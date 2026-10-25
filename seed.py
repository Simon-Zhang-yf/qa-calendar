"""Reset the local testing database to the fake fixture in seed_data.json."""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from auth import hash_password
from database import ROOT, connect, default_database_path, initialize
from validation import EventInput

SEED_FILE = ROOT / "seed_data.json"


def next_tuesday(today: date) -> date:
    days = (1 - today.weekday()) % 7
    return today + timedelta(days=days or 7)


def reset_database(path: Path, today: date | None = None) -> date:
    today = today or datetime.now(ZoneInfo("America/Boise")).date()
    event_date = next_tuesday(today)
    data = json.loads(SEED_FILE.read_text())
    initialize(path)
    with connect(path) as db:
        db.execute("DELETE FROM events")
        db.execute("DELETE FROM users")
        owners = {}
        for user in data["users"]:
            owners[user["username"]] = user["id"]
            db.execute("INSERT INTO users VALUES (?, ?, ?)", (
                user["id"], user["username"], hash_password(user["password"]),
            ))
        for item in data["events"]:
            fields = {key: value for key, value in item.items() if key != "owner"}
            event = EventInput(**fields, date=event_date.isoformat())
            db.execute(
                """INSERT INTO events (owner_id, title, date, start_time, end_time, private)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (owners[item["owner"]], *event.database_values()),
            )
    return event_date


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=default_database_path())
    parser.add_argument("--today", type=date.fromisoformat, help="Reference date YYYY-MM-DD for repeatable tests")
    args = parser.parse_args()
    seeded_date = reset_database(args.database, args.today)
    print(f"Reset {args.database}. Seeded Tuesday events: {seeded_date} (Alice 14:00–15:00).")
