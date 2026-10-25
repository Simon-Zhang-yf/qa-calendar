"""Small SQLite persistence layer. Visibility filtering happens in SQL."""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from dotenv import dotenv_values

from validation import EventInput

ROOT = Path(__file__).resolve().parent


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name, dotenv_values(ROOT / ".env").get(name) or default)


def default_database_path() -> Path:
    path = Path(setting("DATABASE_PATH", "qa-calendar.sqlite3"))
    return path if path.is_absolute() else ROOT / path


@contextmanager
def connect(path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path):
    with connect(path) as db:
        db.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY,
            owner_id INTEGER NOT NULL REFERENCES users(id),
            title TEXT NOT NULL CHECK(length(trim(title)) BETWEEN 1 AND 200),
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL CHECK(end_time > start_time),
            private INTEGER NOT NULL DEFAULT 0 CHECK(private IN (0, 1))
        )""")


def find_user(path, *, user_id=None, username=None):
    with connect(path) as db:
        if user_id is not None:
            return db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()


def event_dict(row):
    event = dict(row)
    event["private"] = bool(event["private"])
    return event


EVENT_SELECT = """SELECT events.*, users.username AS owner
                  FROM events JOIN users ON users.id = events.owner_id"""


def list_events(path, user_id):
    with connect(path) as db:
        rows = db.execute(
            EVENT_SELECT + " WHERE owner_id = ? OR private = 0 ORDER BY date, start_time, events.id",
            (user_id,),
        ).fetchall()
        return [event_dict(row) for row in rows]


def get_event(path, user_id, event_id):
    with connect(path) as db:
        row = db.execute(
            EVENT_SELECT + " WHERE events.id = ? AND (owner_id = ? OR private = 0)",
            (event_id, user_id),
        ).fetchone()
        return event_dict(row) if row else None


def create_event(path, user_id, event: EventInput):
    with connect(path) as db:
        cursor = db.execute(
            """INSERT INTO events (owner_id, title, date, start_time, end_time, private)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, *event.database_values()),
        )
        event_id = cursor.lastrowid
    return get_event(path, user_id, event_id)
