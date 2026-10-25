from datetime import date

import pytest

from database import connect
from seed import next_tuesday, reset_database


@pytest.mark.parametrize("reference,expected", [
    ("2026-10-24", "2026-10-27"),
    ("2026-10-26", "2026-10-27"),
    ("2026-10-27", "2026-11-03"),
    ("2026-12-31", "2027-01-05"),
])
def test_next_tuesday_is_strictly_future(reference, expected):
    assert next_tuesday(date.fromisoformat(reference)).isoformat() == expected


def test_reset_removes_changes_and_restores_known_state(database_path, client, login, event_payload):
    login()
    assert client.post("/api/events", json=event_payload).status_code == 201
    reset_database(database_path, date(2026, 10, 24))
    reset_database(database_path, date(2026, 10, 24))
    with connect(database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 4
        event = dict(db.execute("SELECT * FROM events WHERE id = 1").fetchone())
    assert event["owner_id"] == 1
    assert (event["date"], event["start_time"], event["end_time"]) == ("2026-10-27", "14:00", "15:00")
