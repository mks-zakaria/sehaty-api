"""Request/response DTOs for the doctor-availability surface.

No business logic, no DB access. `*In` models parse the request body; `*Out`
models translate a `sehaty.db.Availability` ORM row into the JSON contract.
"""

from datetime import date, time

from pydantic import BaseModel, ConfigDict


class AvailabilityIn(BaseModel):
    """A recurring weekly availability window the calling doctor adds.

    Maps one-to-one onto `AvailabilityController.add` keyword arguments;
    `weekday` is 0=Monday .. 6=Sunday and validation lives in the controller.
    """

    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int = 30


class AvailabilityOut(BaseModel):
    """One of a doctor's recurring availability windows."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    weekday: int
    start_time: time
    end_time: time
    slot_minutes: int


class AvailabilityExceptionIn(BaseModel):
    """A date-specific override the calling doctor adds to their weekly schedule.

    ``kind`` is ``BLOCK`` (close a day or window) or ``OPEN`` (add a one-off
    window). The cross-field rules (OPEN needs times + a positive
    ``slot_minutes``; a timed BLOCK needs both bounds well-ordered) live in
    ``AvailabilityExceptionController.add`` — an invalid combination surfaces as
    a ``SehatyValidationError`` mapped to 400 by the global handler.
    """

    date: date
    kind: str
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = None
    reason: str | None = None


class AvailabilityExceptionOut(BaseModel):
    """One of a doctor's date-specific availability exceptions."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    date: date
    kind: str
    start_time: time | None = None
    end_time: time | None = None
    slot_minutes: int | None = None
    reason: str | None = None
