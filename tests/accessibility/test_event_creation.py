"""Run axe on the complete, signed-in event creation page in real Chromium."""

import json
import socket
import threading
import time

import pytest
import uvicorn
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect, sync_playwright

from app import create_app
from database import ROOT


@pytest.fixture
def live_calendar_url(database_path, monkeypatch):
    """Serve an isolated seeded database on an OS-assigned localhost port."""
    monkeypatch.setenv("COOKIE_SECURE", "false")
    app = create_app(database_path, "fake-accessibility-test-session-key")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert server.started, "The isolated accessibility test server did not start."
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "The accessibility test server did not stop."


def test_event_creation_page_has_no_serious_or_critical_axe_violations(
    live_calendar_url, seed_data, monkeypatch,
):
    """Audit the whole event creation page; fail on every serious/critical rule."""
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright-browsers"))
    report_dir = ROOT / "test-results" / "accessibility"
    report_dir.mkdir(parents=True, exist_ok=True)
    account = next(user for user in seed_data["users"] if user["username"] == "alice")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            response = page.goto(f"{live_calendar_url}/login")
            assert response.status == 200
            page.get_by_test_id("login-username").fill(account["username"])
            page.get_by_test_id("login-password").fill(account["password"])
            page.get_by_test_id("login-button").click()
            page.wait_for_url(f"{live_calendar_url}/")
            # Pin the month so the full calendar and seeded content are repeatable.
            response = page.goto(f"{live_calendar_url}/?month=2026-10")
            assert response.status == 200
            expect(page.get_by_test_id("current-user")).to_have_text("alice")
            expect(page.get_by_test_id("event-title-input")).to_be_visible()
            expect(page.get_by_test_id("create-event-button")).to_be_visible()
            page.wait_for_load_state("networkidle")

            results = Axe().run(page)
            response_data = results.response
            (report_dir / "event-creation-axe.json").write_text(
                json.dumps(response_data, indent=2), encoding="utf-8"
            )
            page.screenshot(path=str(report_dir / "event-creation.png"), full_page=True)
        finally:
            browser.close()

    violations = response_data["violations"]
    blocking = [violation for violation in violations if violation["impact"] in {"serious", "critical"}]
    print(f"axe: {len(violations)} total violations; {len(blocking)} serious/critical violations.")
    assert not blocking, (
        "Serious/critical accessibility violations on the event creation page:\n"
        + json.dumps(blocking, indent=2)
    )
