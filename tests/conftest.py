import json
import shutil
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import create_app
from seed import SEED_FILE, reset_database

# Explicitly fake configuration, used only by isolated tests.
TEST_SECRET = "fake-test-session-key-never-use-outside-tests"
REFERENCE_DATE = date(2026, 10, 24)


def pytest_configure(config):
    # Pytest creates basetemp itself, but its parent must already exist.
    (config.rootpath / "test-results").mkdir(exist_ok=True)


@pytest.fixture(scope="session")
def seed_data():
    return json.loads(SEED_FILE.read_text())


@pytest.fixture(scope="session")
def seeded_database(tmp_path_factory):
    path = tmp_path_factory.mktemp("seed") / "seed.sqlite3"
    reset_database(path, REFERENCE_DATE)
    return path


@pytest.fixture
def database_path(tmp_path, seeded_database):
    path = tmp_path / "calendar.sqlite3"
    shutil.copyfile(seeded_database, path)
    return path


@pytest.fixture
def client(database_path):
    with TestClient(create_app(database_path, TEST_SECRET)) as client:
        yield client


@pytest.fixture
def login(client, seed_data):
    def sign_in(username="alice"):
        account = next(user for user in seed_data["users"] if user["username"] == username)
        response = client.post(
            "/login", data={"username": username, "password": account["password"]},
            follow_redirects=False,
        )
        assert response.status_code == 303
        return response
    return sign_in


@pytest.fixture
def event_payload(seed_data):
    return {
        key: value for key, value in seed_data["events"][0].items() if key != "owner"
    } | {"date": "2026-10-27"}
