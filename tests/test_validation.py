import pytest
from pydantic import ValidationError

from validation import EventInput


def test_valid_event_and_trimmed_title(event_payload):
    event_payload["title"] = "  " + event_payload["title"] + "  "
    event = EventInput(**event_payload)
    assert event.title == "Alice's Tuesday planning"
    assert event.database_values() == (
        "Alice's Tuesday planning", "2026-10-27", "14:00", "15:00", 0,
    )


@pytest.mark.parametrize("field", ["title", "date", "start_time", "end_time"])
def test_required_fields(event_payload, field):
    del event_payload[field]
    with pytest.raises(ValidationError):
        EventInput(**event_payload)


@pytest.mark.parametrize("patch", [
    {"title": ""}, {"title": " \t "}, {"title": "A" * 201}, {"title": None},
    {"date": ""}, {"date": "2026-02-30"}, {"date": "10/27/2026"}, {"date": 0},
    {"start_time": "25:00"}, {"end_time": "15:60"}, {"start_time": "2 PM"},
    {"start_time": "14:00:00"}, {"end_time": "15:00+01:00"},
    {"end_time": "14:00"}, {"end_time": "13:59"},
    {"start_time": "23:00", "end_time": "01:00"},
    {"private": "false"}, {"private": 1}, {"owner_id": 2},
])
def test_invalid_input(event_payload, patch):
    with pytest.raises(ValidationError):
        EventInput(**(event_payload | patch))


def test_one_minute_event_is_valid(event_payload):
    assert EventInput(**(event_payload | {"end_time": "14:01"})).end_time.minute == 1
