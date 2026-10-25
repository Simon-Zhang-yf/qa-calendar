"""Validation-only tests using the seeded fake event payload.

Acceptance IDs are included in every test name and docstring. AC-1 boundary
cases exercise valid same-day input; AC-4 and AC-5 exercise time ordering.
These tests call EventInput directly without HTTP requests or a database.
"""

from datetime import date, time

import pytest
from pydantic import ValidationError

from validation import EventInput


@pytest.mark.parametrize("private", [False, True], ids=["public", "private"])
def test_ac_1_valid_input_preserves_event_fields(event_payload, private):
    """AC-1: Valid input produces a complete, correctly typed event."""
    event = EventInput.model_validate(event_payload | {"private": private})

    assert event.title == event_payload["title"]
    assert event.date == date(2026, 10, 27)
    assert event.start_time == time(14, 0)
    assert event.end_time == time(15, 0)
    assert event.private is private


def test_ac_1_unchecked_private_defaults_to_public(event_payload):
    """AC-1: Omitting the private flag keeps the event public."""
    payload = {key: value for key, value in event_payload.items() if key != "private"}

    assert EventInput.model_validate(payload).private is False


def test_ac_1_valid_title_is_trimmed(event_payload):
    """AC-1: Surrounding whitespace is removed from a valid title."""
    event = EventInput.model_validate(
        event_payload | {"title": f"  {event_payload['title']}\t"}
    )

    assert event.title == event_payload["title"]


def test_ac_2_missing_title_is_rejected(event_payload):
    """AC-2: An omitted title produces a required-field error for title."""
    payload = {key: value for key, value in event_payload.items() if key != "title"}

    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(payload)

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("title",)
    assert errors[0]["type"] == "missing"


@pytest.mark.parametrize("title", ["", " \t\n "], ids=["empty", "whitespace"])
def test_ac_2_blank_title_is_rejected(event_payload, title):
    """AC-2: Empty and whitespace-only titles fail the title requirement."""
    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(event_payload | {"title": title})

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("title",)
    assert "Title is required" in errors[0]["msg"]


def test_ac_3_missing_date_is_rejected(event_payload):
    """AC-3: An omitted date produces a required-field error for date."""
    payload = {key: value for key, value in event_payload.items() if key != "date"}

    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(payload)

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("date",)
    assert errors[0]["type"] == "missing"


@pytest.mark.parametrize("event_date", ["", None], ids=["empty", "null"])
def test_ac_3_empty_date_is_rejected(event_payload, event_date):
    """AC-3: An empty or null date cannot satisfy the date requirement."""
    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(event_payload | {"date": event_date})

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ("date",)
    assert "Date is required" in errors[0]["msg"]


@pytest.mark.parametrize("start,end", [
    ("14:00", "13:00"),
    ("14:00", "13:59"),
    ("23:59", "00:00"),
], ids=["one-hour-earlier", "one-minute-earlier", "crosses-midnight"])
def test_ac_4_end_before_start_is_rejected(event_payload, start, end):
    """AC-4: Earlier end times, including overnight input, are rejected."""
    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(event_payload | {"start_time": start, "end_time": end})

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ()
    assert "End time must be after start time on the same date" in errors[0]["msg"]


@pytest.mark.parametrize("same_time", ["00:00", "14:00", "23:59"],
                         ids=["midnight", "afternoon", "last-minute"])
def test_ac_5_equal_start_and_end_is_rejected(event_payload, same_time):
    """AC-5: Zero-duration events fail at midnight and throughout the day."""
    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(
            event_payload | {"start_time": same_time, "end_time": same_time}
        )

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == ()
    assert "End time must be after start time" in errors[0]["msg"]


@pytest.mark.parametrize("start,end,expected_start,expected_end", [
    ("00:00", "00:01", time(0, 0), time(0, 1)),
    ("00:00", "23:59", time(0, 0), time(23, 59)),
    ("23:58", "23:59", time(23, 58), time(23, 59)),
], ids=["one-minute-from-midnight", "first-to-last-minute", "one-minute-before-day-end"])
def test_ac_1_valid_same_day_time_boundaries(
    event_payload, start, end, expected_start, expected_end,
):
    """AC-1: Midnight starts and the last minute of a day are valid boundaries."""
    event = EventInput.model_validate(event_payload | {"start_time": start, "end_time": end})

    assert event.start_time == expected_start
    assert event.end_time == expected_end
    assert event.date == date(2026, 10, 27)


@pytest.mark.parametrize("field", ["start_time", "end_time"])
def test_ac_1_midnight_must_use_00_not_24(event_payload, field):
    """AC-1: A valid clock time cannot use 24:00 for either time field."""
    with pytest.raises(ValidationError) as caught:
        EventInput.model_validate(event_payload | {field: "24:00"})

    errors = caught.value.errors()
    assert len(errors) == 1
    assert errors[0]["loc"] == (field,)
    assert errors[0]["type"] == "time_parsing"
