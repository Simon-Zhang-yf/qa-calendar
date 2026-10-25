import pytest
from fastapi.testclient import TestClient

from app import create_app
from conftest import TEST_SECRET
from database import connect


@pytest.mark.parametrize("method,path", [
    ("get", "/api/events"), ("get", "/api/events/1"), ("post", "/api/events"),
])
def test_api_requires_login(client, event_payload, method, path):
    kwargs = {"json": event_payload} if method == "post" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 401


def test_unauthenticated_invalid_event_still_requires_login(client):
    assert client.post("/api/events", json={}).status_code == 401
    assert client.post("/api/events", content="{", headers={"Content-Type": "application/json"}).status_code == 401


def test_login_logout_and_bad_credentials(client, login, seed_data):
    assert client.get("/", follow_redirects=False).headers["location"] == "/login"
    assert client.get("/login").status_code == 200
    response = client.post("/login", data={"username": "alice", "password": seed_data["users"][1]["password"]})
    assert response.status_code == 401
    assert "Invalid username or password" in response.text
    response = login()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/events").status_code == 200
    assert client.get("/login", follow_redirects=False).status_code == 303
    assert client.post("/logout", follow_redirects=False).status_code == 303
    assert client.get("/api/events").status_code == 401


@pytest.mark.parametrize("username,own_private,other_private", [("alice", 2, 4), ("bob", 4, 2)])
def test_visibility_in_list_detail_and_html(client, login, username, own_private, other_private, seed_data):
    login(username)
    response = client.get("/api/events")
    assert response.status_code == 200
    assert {event["id"] for event in response.json()} == {1, 3, own_private}
    for event_id in (1, 3, own_private):
        assert client.get(f"/api/events/{event_id}").status_code == 200
    hidden = client.get(f"/api/events/{other_private}")
    missing = client.get("/api/events/99999")
    assert hidden.status_code == missing.status_code == 404
    assert hidden.json() == missing.json()
    page = client.get("/?month=2026-10")
    assert page.status_code == 200
    assert f'data-event-id="{own_private}"' in page.text
    assert f'data-event-id="{other_private}"' not in page.text
    assert seed_data["events"][other_private - 1]["title"] not in page.text


@pytest.mark.parametrize("private", [True, False])
def test_create_event_ownership_visibility_and_persistence(client, login, event_payload, private, database_path):
    login("alice")
    response = client.post("/api/events", json=event_payload | {"private": private})
    assert response.status_code == 201
    event = response.json()
    assert event["owner"] == "alice"
    assert event["owner_id"] == 1
    assert event["private"] is private
    assert event["date"] == "2026-10-27"
    login("bob")
    assert client.get(f'/api/events/{event["id"]}').status_code == (404 if private else 200)
    visible_ids = {item["id"] for item in client.get("/api/events").json()}
    assert (event["id"] in visible_ids) is (not private)
    with TestClient(create_app(database_path, TEST_SECRET)) as restarted:
        restarted.post("/login", data={"username": "alice", "password": "alice-test-only"})
        assert restarted.get(f'/api/events/{event["id"]}').json() == event


@pytest.mark.parametrize("patch", [
    {"title": ""}, {"title": "  "}, {"date": ""}, {"date": "2026-02-30"},
    {"end_time": "14:00"}, {"end_time": "13:00"}, {"start_time": "25:00"},
    {"private": "false"}, {"owner_id": 2},
])
def test_invalid_api_input_does_not_create_events(client, login, event_payload, patch):
    login()
    before = client.get("/api/events").json()
    response = client.post("/api/events", json=event_payload | patch)
    assert response.status_code == 422
    assert client.get("/api/events").json() == before


def test_missing_fields_and_malformed_json(client, login):
    login()
    assert client.post("/api/events", json={}).status_code == 422
    assert client.post("/api/events", content="{", headers={"Content-Type": "application/json"}).status_code == 422


@pytest.mark.parametrize("private", [True, False])
def test_html_creation_and_validation(client, login, event_payload, private):
    login()
    form = {key: value for key, value in event_payload.items() if key != "private"}
    if private:
        form["private"] = "on"
    response = client.post("/events", data=form, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/?month=2026-10"
    created = client.get("/api/events/5").json()
    assert created["private"] is private
    form["end_time"] = form["start_time"]
    response = client.post("/events", data=form)
    assert response.status_code == 422
    assert "End time must be after start time" in response.text
    assert 'data-testid="event-errors"' in response.text
    assert 'value="14:00"' in response.text
    assert len(client.get("/api/events").json()) == 4


def test_html_escapes_event_titles(client, login, event_payload):
    login()
    client.post("/api/events", json=event_payload | {"title": "<script>alert('fake')</script>"})
    html = client.get("/?month=2026-10").text
    assert "<script>alert(" not in html
    assert "&lt;script&gt;" in html


def test_stable_form_selectors_and_stylesheet(client, login):
    for selector in ("login-username", "login-password", "login-button"):
        assert f'data-testid="{selector}"' in client.get("/login").text
    login()
    page = client.get("/")
    for selector in (
        "event-title-input", "event-date", "event-start-time", "event-end-time",
        "event-private", "create-event-button", "logout-button", "calendar",
        "previous-month", "next-month", "today-button",
    ):
        assert f'data-testid="{selector}"' in page.text
    assert client.get("/static/styles.css").status_code == 200


def test_bad_month_is_validation_error(client, login):
    login()
    assert client.get("/?month=garbage").status_code == 422


def test_tampered_cookie_cannot_authenticate(client, login):
    login()
    client.cookies.set("session", "fake-tampered-session")
    assert client.get("/api/events").status_code == 401


def test_passwords_are_hashed_in_database(database_path, seed_data):
    from auth import verify_password
    with connect(database_path) as db:
        users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    for user, seeded in zip(users, seed_data["users"], strict=True):
        assert user["password_hash"] != seeded["password"]
        assert verify_password(seeded["password"], user["password_hash"])


@pytest.mark.parametrize("secret", ["", "change-me"])
def test_placeholder_session_secret_rejected(database_path, secret):
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app(database_path, secret)
