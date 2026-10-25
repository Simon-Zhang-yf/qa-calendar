"""Shared event validation for HTML forms, the JSON API, and seed data."""

import re
from datetime import date, time
from typing import Self

from pydantic import BaseModel, ConfigDict, StrictBool, field_validator, model_validator


class EventInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    date: date
    start_time: time
    end_time: time
    private: StrictBool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Title is required.")
        if len(value) > 200:
            raise ValueError("Title must be 200 characters or fewer.")
        return value

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("Date is required in YYYY-MM-DD format.")
        return value

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def validate_time(cls, value: object) -> object:
        if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
            raise ValueError("Time is required in HH:MM format (24-hour clock).")
        return value

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time on the same date.")
        return self

    def database_values(self) -> tuple:
        return (
            self.title, self.date.isoformat(), self.start_time.strftime("%H:%M"),
            self.end_time.strftime("%H:%M"), int(self.private),
        )
