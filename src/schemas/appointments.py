"""Request/response DTOs for the appointments surface — boundary translation.

No business logic, no DB access. `*In` models parse the request body; `*Out`
models translate a `sehaty.db.Appointment` ORM row (or a slot tuple projected
into `SlotOut`) into the JSON contract clients consume.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sehaty.db import AppointmentStatus


class AppointmentIn(BaseModel):
    """A patient's booking request (the `POST /appointments` body).

    Maps one-to-one onto `AppointmentController.book`: `start_at` must be a
    genuine free slot for `doctor_id` (validated in core, else a 409).
    """

    doctor_id: int
    start_at: datetime
    reason: str | None = None


class AppointmentTransitionIn(BaseModel):
    """A status transition (the `PATCH /appointments/{id}` body).

    `status` is coerced to the `AppointmentStatus` StrEnum; the role-based
    transition matrix is enforced by the controller.
    """

    status: AppointmentStatus
    notes: str | None = None


class AppointmentOut(BaseModel):
    """An appointment as seen by its patient or doctor."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    doctor_id: int
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    reason: str | None = None
    notes: str | None = None


class PatientAppointmentOut(BaseModel):
    """A patient's own appointment, carrying the doctor's human-readable name.

    Translates the core ``PatientAppointmentRow`` projection (from
    ``AppointmentController.list_for_patient_view``): ``doctor_name`` resolves to
    the doctor's profile name, falling back to ``"Doctor #{id}"``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    doctor_name: str
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    reason: str | None = None


class SlotOut(BaseModel):
    """One free bookable slot for a doctor (a `(start, end)` pair)."""

    start_at: datetime
    end_at: datetime
