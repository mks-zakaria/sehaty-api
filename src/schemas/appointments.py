"""Request/response DTOs for the appointments surface — boundary translation.

No business logic, no DB access. `*In` models parse the request body; `SlotOut`
translates a slot ``(start, end)`` tuple into the JSON contract. The appointment
responses themselves are served directly from the core projections
(``AppointmentRow`` / ``PatientAppointmentRow`` / ``AppointmentGridRow``).
"""

from datetime import datetime

from pydantic import BaseModel
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


class RescheduleIn(BaseModel):
    """A reschedule request (the `POST /{id}/reschedule` body).

    Maps one-to-one onto `AppointmentController.reschedule`: `new_start_at` must
    be a genuine free slot for the appointment's doctor (validated in core, else
    a 409). Shared by the patient route and the doctor/assistant route.
    """

    new_start_at: datetime
    notes: str | None = None


class SlotOut(BaseModel):
    """One free bookable slot for a doctor (a `(start, end)` pair)."""

    start_at: datetime
    end_at: datetime
