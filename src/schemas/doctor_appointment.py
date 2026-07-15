"""Request/response DTOs for the doctor/assistant appointment grid.

No business logic, no DB access. `AppointmentGridOut` translates a core
:class:`~sehaty.core.controllers.appointments.AppointmentGridRow` (a detached
frozen dataclass with a human-readable ``patient_name``) into the JSON contract;
`AppointmentTransitionIn` parses the confirm/transition body an assistant sends
on the doctor's behalf.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sehaty.db import AppointmentStatus


class AppointmentTransitionIn(BaseModel):
    """A status transition on a doctor's appointment (confirm-on-behalf body).

    `status` is coerced to the `AppointmentStatus` StrEnum; the role-based
    transition matrix (e.g. REQUESTED -> CONFIRMED) is enforced by the core
    controller, which also fires the patient notification.
    """

    status: AppointmentStatus
    notes: str | None = None


class AppointmentGridOut(BaseModel):
    """One appointment in the doctor's booking-slot grid, patient name resolved.

    Mirrors the core ``AppointmentGridRow`` projection: ``patient_name`` is always
    human-readable and ``clinic_patient_id``/``patient_phone`` may be ``None``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    clinic_patient_id: int | None = None
    patient_name: str
    patient_phone: str | None = None
    start_at: datetime
    end_at: datetime
    status: AppointmentStatus
    reason: str | None = None
