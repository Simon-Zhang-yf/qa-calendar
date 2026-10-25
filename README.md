# qa-calendar

A small local testing calendar built with FastAPI, Jinja2, and SQLite. It has
session login, a month calendar, an event form, and a JSON API. Use Python 3.11+.
All accounts and events are fake test data.

## First-time setup (macOS / Linux)

```sh
cd "/Users/yifuzhang/Desktop/BYUI 2026 Fall/CSE290/qa-calendar"
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -c 'from pathlib import Path; import secrets; Path(".env").write_text("SECRET_KEY=" + secrets.token_urlsafe(32) + "\n")'
python seed.py
pytest
uvicorn app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

The secret-generation command replaces `.env`; use it during first-time setup
only. `.env` is ignored by Git. The app reads it automatically and rejects a
missing secret or the `change-me` placeholder. Never commit real secrets.

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

On later runs, use:

```sh
cd "/Users/yifuzhang/Desktop/BYUI 2026 Fall/CSE290/qa-calendar"
source .venv/bin/activate
uvicorn app:create_app --factory --reload --host 127.0.0.1 --port 8000
```

On Windows PowerShell, create the environment with `python -m venv .venv`, activate
with `.venv\Scripts\Activate.ps1`, and copy the config with
`Copy-Item .env.example .env`. Replace `change-me` with a randomly generated secret
in `.env`, then run the same installation, seed, test, and server commands.

## Fake testing accounts and database reset

`seed_data.json` is the source of the fake test usernames and passwords:

| Username | Fake test password |
| --- | --- |
| alice | alice-test-only |
| bob | bob-test-only |

These credentials are only for this local testing app. The running app checks
salted password hashes in SQLite; it does not read passwords from the seed file.
There is no signup or real account data.

```sh
python seed.py
```

**This resets all users and events in the configured database.** It creates the
two accounts plus a public and a private event for each. Alice's public event is
on next Tuesday from **14:00 to 15:00 (2–3 PM)**. “Next Tuesday” means strictly
after today, using America/Boise for today's date. If run on a Tuesday, it uses
the following Tuesday. Event dates and times are local wall-clock values without
timezone conversion.

For a repeatable reference date:

```sh
python seed.py --today 2026-10-24
```

This seeds Alice's event on October 27, 2026. The default database is
`qa-calendar.sqlite3` in this project. Optional `DATABASE_PATH` in `.env` or the
environment changes it; relative paths resolve from the project folder. The seed
command also accepts `--database PATH`. Optional `COOKIE_SECURE=true` requires
HTTPS for session cookies; leave it unset for local HTTP.

## Events and API

Sign in through `/login`, then create events in the calendar sidebar. Signed-in
users see their own public and private events and everyone else's public events.
Other users' private events are excluded from both the HTML and JSON responses.

All three API routes use the session cookie set by the login form:

| Method | Path | Successful result |
| --- | --- | --- |
| POST | `/api/events` | `201`, created event object |
| GET | `/api/events` | `200`, array of visible event objects |
| GET | `/api/events/{id}` | `200`, visible event object |

Example POST body:

```json
{
  "title": "Alice's Tuesday planning",
  "date": "2026-10-27",
  "start_time": "14:00",
  "end_time": "15:00",
  "private": false
}
```

The server assigns ownership from the session. `private` defaults to `false` and
must be a JSON boolean when provided. Titles are trimmed, required, and limited
to 200 characters. Dates use `YYYY-MM-DD`; both times are required in 24-hour
`HH:MM` format. End time must be strictly later on the same date. Overnight
events are not supported. Unknown JSON fields are rejected.

API responses use `401` when not logged in, `404` for missing events or someone
else's private events, and `422` for invalid input. The web form also returns
`422` and displays validation errors. Interactive API documentation is at `/docs`.

## Tests and automation selectors

Install Chromium for the accessibility test once after installing requirements:

```sh
PLAYWRIGHT_BROWSERS_PATH=.playwright-browsers python -m playwright install chromium --only-shell
```

On Windows PowerShell, first set `$env:PLAYWRIGHT_BROWSERS_PATH = ".playwright-browsers"`,
then run `python -m playwright install chromium --only-shell`.

```sh
pytest
```

Tests seed isolated SQLite databases under ignored `test-results/tmp`; they do
not reset the app database. They cover shared validation, session login/logout,
ownership, public/private visibility in HTML and JSON, error codes, persistence,
HTML escaping, and repeatable seeding. Project rules are in `AGENTS.md`.

Run the focused security and accessibility checks with:

```sh
python -m pytest tests/security/test_authorization.py tests/accessibility/test_event_creation.py -v -s
```

The accessibility test starts its own local server, signs in with seeded fake
data, and audits the entire event creation page with `axe-playwright-python`.
It fails on serious or critical violations without disabling rules or excluding
elements. Its full axe report and screenshot are saved under
`test-results/accessibility/`. These automated checks do not replace manual
accessibility testing.

Stable `data-testid` values:

- Login: `login-username`, `login-password`, `login-button`, `login-error`.
- Event form: `event-title-input`, `event-date`, `event-start-time`,
  `event-end-time`, `event-private`, `create-event-button`, `event-errors`.
- Calendar: `calendar`, `event-card`, `event-title`, `previous-month`,
  `next-month`, `today-button`, `current-user`, `logout-button`.

Event cards also have `data-event-id`; calendar cells have `data-date`.
`validation.py` contains `EventInput`, shared by forms, the API, and the seed
script. SQLite queries enforce visibility in `database.py`.
