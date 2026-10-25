# Acceptance criteria

Use only the fake users and event data from `seed_data.json`. Start each scenario
with a reset database unless the scenario explicitly creates an event first.

## AC-1 — Create a valid event

**Given** Alice is signed in with her seeded fake account,
**When** she creates an event titled “Alice's Tuesday planning” dated
`2026-10-27`, starting at `14:00` and ending at `15:00`, with Private unchecked,
**Then** the event is saved with Alice as its owner and appears on the calendar
for that date as a public event. Creating the same valid input through
`POST /api/events` returns `201` with the saved event.

## AC-2 — Require a title

**Given** Alice is signed in and all other event fields are valid,
**When** she attempts to create an event with a missing, empty, or whitespace-only
title,
**Then** the event is not saved and validation identifies the title as required.
The web form prevents submission or displays a validation error; a direct form
submission or `POST /api/events` with an invalid title returns `422`.

## AC-3 — Require a date

**Given** Alice is signed in and all other event fields are valid,
**When** she attempts to create an event with a missing or empty date,
**Then** the event is not saved and validation identifies the date as required.
The web form prevents submission or displays a validation error; a direct form
submission or `POST /api/events` with an invalid date returns `422`.

## AC-4 — Reject an end time before the start time

**Given** Alice is signed in and has entered a valid title and date,
**When** she submits an event starting at `14:00` and ending at `13:00`,
**Then** the event is not saved, the web form explains that the end time must be
after the start time, and `POST /api/events` with the same input returns `422`.

## AC-5 — Reject equal start and end times

**Given** Alice is signed in and has entered a valid title and date,
**When** she submits an event with both start and end time set to `14:00`,
**Then** the event is not saved, the web form explains that the end time must be
after the start time, and `POST /api/events` with the same input returns `422`.

## AC-6 — Persist events after refresh

**Given** Alice has successfully created an event using the valid fake input in
AC-1 and is viewing its calendar month,
**When** she refreshes the page,
**Then** the saved event remains visible with the same title, date, times,
owner, and privacy setting, without creating an additional copy. The event also
remains available through `GET /api/events` and `GET /api/events/{id}`.

## AC-7 — Enforce privacy between users

**Given** the seeded database contains public and private events for Alice and
Bob,
**When** either user signs in and views the calendar or requests
`GET /api/events`,
**Then** they see all their own events and the other user's public events, with
none of the other user's private events or their details included. Requesting
`GET /api/events/{id}` for the other user's private event returns `404`, just as
for a nonexistent event; requesting their own private event or a public event
returns `200`.

## AC-8 — Require authentication

**Given** a visitor has no valid signed-in session, including after logging out,
**When** they open the calendar page,
**Then** they are redirected to the login page and no event data is displayed.
Requests to `POST /api/events`, `GET /api/events`, or `GET /api/events/{id}` return
`401`, and an unauthenticated event-creation attempt saves no event.
