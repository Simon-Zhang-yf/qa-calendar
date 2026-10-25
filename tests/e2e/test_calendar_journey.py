"""AC-1, AC-6, AC-7: A real browser journey using pytest-playwright fixtures."""

import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Page, expect

from app import create_app
from database import ROOT


@pytest.fixture(scope="session", autouse=True)
def project_browser_environment():
    """Use the Chromium installation kept inside this project."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".playwright-browsers"))
        yield


@pytest.fixture(scope="session")
def _pw_artifacts_folder(pytestconfig):
    """Keep pytest-playwright's staging files inside the project as well."""
    folder = tempfile.TemporaryDirectory(prefix="playwright-staging-", dir=ROOT / "test-results")
    yield folder
    # The plugin moves final screenshots/traces after fixture teardown completes.
    pytestconfig.add_cleanup(folder.cleanup)


@pytest.fixture
def e2e_app_url(tmp_path, monkeypatch):
    """Reset a fresh SQLite database with the seed CLI, then serve the real app."""
    database_path = tmp_path / "e2e-calendar.sqlite3"
    reset = subprocess.run(
        [
            sys.executable, str(ROOT / "seed.py"),
            "--database", str(database_path), "--today", "2026-10-24",
        ],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert reset.returncode == 0, reset.stdout + reset.stderr
    monkeypatch.setenv("COOKIE_SECURE", "false")
    app = create_app(database_path, "fake-e2e-session-key-never-use-outside-tests")
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
            assert server.started, "The isolated E2E app did not start."
            yield f"http://127.0.0.1:{port}"
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "The isolated E2E app did not stop."


def sign_in(page: Page, account):
    page.get_by_test_id("login-username").fill(account["username"])
    page.get_by_test_id("login-password").fill(account["password"])
    page.get_by_test_id("login-button").click()
    expect(page.get_by_test_id("current-user")).to_have_text(account["username"])


@pytest.mark.browser_context_args(viewport={"width": 1440, "height": 1000})
def test_ac_1_ac_6_ac_7_private_event_survives_reload_and_is_hidden_from_bob(
    page: Page, e2e_app_url, seed_data, event_payload, output_path,
):
    """Create as Alice, reload, switch to Bob, and verify private-event isolation."""
    accounts = {account["username"]: account for account in seed_data["users"]}
    private_event = next(
        event for event in seed_data["events"]
        if event["owner"] == "alice" and event["private"]
    )
    event_date = event_payload["date"]
    month_url = f"{e2e_app_url}/?month={event_date[:7]}"

    page.goto(f"{e2e_app_url}/login")
    sign_in(page, accounts["alice"])
    page.goto(month_url)
    matching_cards = page.get_by_test_id("event-card").filter(
        has=page.get_by_test_id("event-title").get_by_text(private_event["title"], exact=True)
    )
    expect(matching_cards).to_have_count(1)
    seeded_ids = {card.get_attribute("data-event-id") for card in matching_cards.all()}

    page.get_by_test_id("event-title-input").fill(private_event["title"])
    page.get_by_test_id("event-date").fill(event_date)
    page.get_by_test_id("event-start-time").fill(private_event["start_time"])
    page.get_by_test_id("event-end-time").fill(private_event["end_time"])
    page.get_by_test_id("event-private").check()
    with page.expect_response(
        lambda response: response.url == f"{e2e_app_url}/events"
        and response.request.method == "POST"
    ) as submission:
        page.get_by_test_id("create-event-button").click()
    assert submission.value.status == 303
    expect(page).to_have_url(month_url)
    expect(matching_cards).to_have_count(2)
    created_ids = {
        card.get_attribute("data-event-id") for card in matching_cards.all()
    } - seeded_ids
    assert len(created_ids) == 1
    created_id = created_ids.pop()
    assert created_id is not None

    page.reload()
    expect(page.get_by_test_id("current-user")).to_have_text("alice")
    expect(matching_cards).to_have_count(2)
    refreshed_cards = matching_cards.all()
    assert created_id in {card.get_attribute("data-event-id") for card in refreshed_cards}
    created_card = next(
        card for card in refreshed_cards if card.get_attribute("data-event-id") == created_id
    )
    expect(created_card.get_by_test_id("event-title")).to_have_text(private_event["title"])
    expect(created_card).to_contain_text(
        f"{private_event['start_time']}–{private_event['end_time']}"
    )
    expect(created_card).to_contain_text("alice · Private")
    artifacts = Path(output_path)
    artifacts.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(artifacts / "alice-after-refresh.png"), full_page=True)

    page.get_by_test_id("logout-button").click()
    expect(page).to_have_url(f"{e2e_app_url}/login")
    expect(page.get_by_test_id("login-button")).to_be_visible()
    sign_in(page, accounts["bob"])
    page.goto(month_url)
    expect(page.get_by_test_id("current-user")).to_have_text("bob")
    expect(page.get_by_test_id("calendar")).to_be_visible()
    expect(matching_cards).to_have_count(0)
    assert created_id not in {
        card.get_attribute("data-event-id") for card in page.get_by_test_id("event-card").all()
    }
    # Public Alice data and Bob's own private data prove the correct month is loaded.
    for event in seed_data["events"]:
        title = page.get_by_test_id("event-title").filter(has_text=event["title"])
        if event["owner"] == "alice" and event["private"]:
            expect(title).to_have_count(0)
        else:
            expect(title).to_be_visible()
