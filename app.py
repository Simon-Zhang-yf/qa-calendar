"""Calendar web pages and session-authenticated JSON API."""

import calendar
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from starlette.middleware.sessions import SessionMiddleware

from auth import verify_password
from database import (
    ROOT, create_event, default_database_path, find_user, get_event,
    initialize, list_events, setting,
)
from validation import EventInput


def create_app(database_path: Path | None = None, secret_key: str | None = None) -> FastAPI:
    secret = secret_key if secret_key is not None else setting("SECRET_KEY")
    if not secret or secret == "change-me":
        raise RuntimeError("Set a private SECRET_KEY in .env before starting. See README.md.")
    db_path = Path(database_path) if database_path is not None else default_database_path()
    initialize(db_path)
    app = FastAPI(title="qa-calendar")
    app.state.database_path = db_path
    app.add_middleware(
        SessionMiddleware, secret_key=secret, same_site="strict", max_age=8 * 60 * 60,
        https_only=setting("COOKIE_SECURE", "false").lower() == "true",
    )
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")

    def current_user(request: Request):
        user_id = request.session.get("user_id")
        return find_user(db_path, user_id=user_id) if isinstance(user_id, int) else None

    def require_user(request: Request):
        user = current_user(request)
        if user is None:
            raise HTTPException(status_code=401, detail="Login required.")
        return user

    def calendar_page(request, user, *, errors=None, values=None, status_code=200, month=None):
        today = datetime.now(ZoneInfo("America/Boise")).date()
        month_text = month or request.query_params.get("month", today.strftime("%Y-%m"))
        try:
            selected = date.fromisoformat(month_text + "-01")
            if not 2 <= selected.year <= 9998:
                raise ValueError
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="Month must be YYYY-MM (years 0002–9998).")
        month_index = selected.year * 12 + selected.month - 1
        previous_year, previous_month = divmod(month_index - 1, 12)
        next_year, next_month = divmod(month_index + 1, 12)
        events = list_events(db_path, user["id"])
        by_date = {}
        for event in events:
            by_date.setdefault(event["date"], []).append(event)
        return templates.TemplateResponse(
            request=request, name="calendar.html", status_code=status_code,
            context={
                "user": user, "errors": errors or [], "values": values or {},
                "today": today.isoformat(), "selected": selected,
                "weeks": calendar.Calendar(firstweekday=6).monthdatescalendar(selected.year, selected.month),
                "by_date": by_date,
                "previous_month": f"{previous_year:04d}-{previous_month + 1:02d}",
                "next_month": f"{next_year:04d}-{next_month + 1:02d}",
            },
        )

    @app.get("/login")
    def login_page(request: Request):
        if current_user(request):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse(request=request, name="login.html", context={"error": None})

    @app.post("/login")
    async def login(request: Request):
        form = await request.form()
        username, password = form.get("username", ""), form.get("password", "")
        user = find_user(db_path, username=username) if isinstance(username, str) else None
        if user is None or not isinstance(password, str) or not verify_password(password, user["password_hash"]):
            return templates.TemplateResponse(
                request=request, name="login.html", status_code=401,
                context={"error": "Invalid username or password."},
            )
        request.session.clear()
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)

    @app.post("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/")
    def home(request: Request):
        user = current_user(request)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        return calendar_page(request, user)

    @app.post("/events")
    async def submit_event(request: Request, user=Depends(require_user)):
        form = await request.form()
        values = {name: form.get(name, "") for name in ("title", "date", "start_time", "end_time")}
        values["private"] = form.get("private") == "on"
        try:
            event = EventInput.model_validate(values)
        except ValidationError as exc:
            return calendar_page(
                request, user, errors=[error["msg"] for error in exc.errors()],
                values=values, status_code=422,
            )
        create_event(db_path, user["id"], event)
        return RedirectResponse(f"/?month={event.date.strftime('%Y-%m')}", status_code=303)

    @app.post("/api/events", status_code=201, openapi_extra={
        "requestBody": {"required": True, "content": {
            "application/json": {"schema": EventInput.model_json_schema()}
        }}
    })
    async def api_create_event(request: Request, user=Depends(require_user)):
        # Authenticate before parsing so even malformed anonymous requests get 401.
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HTTPException(status_code=422, detail="A valid JSON object is required.")
        try:
            event = EventInput.model_validate(payload)
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail=json.loads(exc.json(include_url=False)))
        return create_event(db_path, user["id"], event)

    @app.get("/api/events")
    def api_list_events(user=Depends(require_user)):
        return list_events(db_path, user["id"])

    @app.get("/api/events/{event_id}")
    def api_get_event(event_id: int, user=Depends(require_user)):
        event = get_event(db_path, user["id"], event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Event not found.")
        return event

    return app
