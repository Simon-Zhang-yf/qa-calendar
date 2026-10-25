"""API integration tests against a database reset by seed.py for every test."""

import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import create_app
from database import ROOT


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    """Run the real seed CLI on a fresh, isolated database before each test."""
    database_path = tmp_path / "api-test.sqlite3"
    result = subprocess.run(
        [
            sys.executable, str(ROOT / "seed.py"),
            "--database", str(database_path), "--today", "2026-10-24",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert database_path.is_file()

    # Keep HTTP test sessions independent of local HTTPS cookie configuration.
    monkeypatch.setenv("COOKIE_SECURE", "false")
    app = create_app(
        database_path=database_path,
        secret_key="fake-api-test-session-key-never-use-outside-tests",
    )
    with TestClient(app) as client:
        yield client


def sign_in(client, seed_data, username="alice"):
    account = next(user for user in seed_data["users"] if user["username"] == username)
    response = client.post(
        "/login",
        data={"username": account["username"], "password": account["password"]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return account


@pytest.mark.parametrize("username", ["alice", "bob"])
def test_ac_1_create_event_then_find_it_with_get(api_client, seed_data, event_payload, username):
    """AC-1: A session-authenticated POST persists an event retrievable by GET."""
    account = sign_in(api_client, seed_data, username)
    before = api_client.get("/api/events")
    assert before.status_code == 200
    assert len(before.json()) == 3
    before_ids = {event["id"] for event in before.json()}

    response = api_client.post("/api/events", json=event_payload)

    assert response.status_code == 201
    created = response.json()
    assert created["id"] not in before_ids
    assert created["owner_id"] == account["id"]
    assert created["owner"] == username
    for field, expected in event_payload.items():
        assert created[field] == expected

    detail = api_client.get(f"/api/events/{created['id']}")
    assert detail.status_code == 200
    assert detail.json() == created

    listing = api_client.get("/api/events")
    assert listing.status_code == 200
    assert len(listing.json()) == len(before.json()) + 1
    assert [event for event in listing.json() if event["id"] == created["id"]] == [created]


@pytest.mark.parametrize("changes,missing_field", [
    pytest.param({}, "title", id="AC-2-missing-title"),
    pytest.param({"title": " \t "}, None, id="AC-2-blank-title"),
    pytest.param({}, "date", id="AC-3-missing-date"),
    pytest.param({"date": ""}, None, id="AC-3-empty-date"),
    pytest.param({"end_time": "13:00"}, None, id="AC-4-end-before-start"),
    pytest.param({"end_time": "14:00"}, None, id="AC-5-end-equals-start"),
])
def test_invalid_event_returns_422_without_saving(
    api_client, seed_data, event_payload, changes, missing_field,
):
    """AC-2–AC-5: Invalid input is rejected without changing saved events."""
    sign_in(api_client, seed_data)
    before = api_client.get("/api/events")
    assert before.status_code == 200
    assert len(before.json()) == 3
    payload = event_payload | changes
    if missing_field:
        del payload[missing_field]

    response = api_client.post("/api/events", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"]
    after = api_client.get("/api/events")
    assert after.status_code == 200
    assert after.json() == before.json()


@pytest.mark.parametrize("method,path", [
    pytest.param("post", "/api/events", id="POST-events"),
    pytest.param("get", "/api/events", id="GET-events"),
    pytest.param("get", "/api/events/1", id="GET-event-detail"),
])
def test_ac_8_unauthenticated_request_returns_401(
    api_client, seed_data, event_payload, method, path,
):
    """AC-8: All event API endpoints require a session; rejected POSTs save nothing."""
    kwargs = {"json": event_payload} if method == "post" else {}

    response = api_client.request(method, path, **kwargs)

    assert response.status_code == 401
    assert response.json() == {"detail": "Login required."}

    # A failed anonymous POST must not add an event to the seeded state.
    sign_in(api_client, seed_data)
    visible = api_client.get("/api/events")
    assert visible.status_code == 200
    assert {event["id"] for event in visible.json()} == {1, 2, 3}
