"""Request/response DTOs for the doctor-availability surface.

No business logic, no DB access. `*In` models parse the request body; `*Out`
models translate a `sehaty.db.Availability` ORM row into the JSON contract.
"""

from datetime import time

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
