"""Appointments router. Body of each handler: parse -> ONE controller call.

No SQLAlchemy here. Patients book concrete slots; the owning patient/doctor
then drive the appointment through the role-based status matrix. Business errors
(the SehatyError taxonomy) are mapped to HTTP by the handler in `main`.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.appointments import AppointmentController
from sehaty.db import User, UserRole

from deps import get_current_user, require_roles
from schemas.appointments import (
    AppointmentIn,
    AppointmentOut,
    AppointmentTransitionIn,
    PatientAppointmentOut,
)

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])

_require_patient = require_roles(UserRole.PATIENT)


@router.post("", response_model=AppointmentOut, status_code=status.HTTP_201_CREATED)
def book_appointment(
    body: AppointmentIn,
    user: User = Depends(_require_patient),
) -> AppointmentOut:
    """Book a free slot as the calling patient (409 if it is not bookable)."""
    appt = AppointmentController.book(user.id, body.doctor_id, body.start_at, body.reason)
    return AppointmentOut.model_validate(appt)


@router.get("", response_model=list[PatientAppointmentOut | AppointmentOut])
def list_appointments(
    user: User = Depends(get_current_user),
) -> list[PatientAppointmentOut] | list[AppointmentOut]:
    """List the caller's appointments (patient: booked; doctor: on their calendar).

    A PATIENT gets the enriched view carrying the resolved ``doctor_name`` (the
    ``PatientAppointmentRow`` projection); every other role keeps the plain
    ``AppointmentOut`` (with ``patient_id``/``doctor_id``) as before.
    """
    if user.role == UserRole.PATIENT:
        rows = AppointmentController.list_for_patient_view(user.id)
        return [PatientAppointmentOut.model_validate(r) for r in rows]
    appts = AppointmentController.list_for(user.id, user.role)
    return [AppointmentOut.model_validate(a) for a in appts]


@router.patch("/{appointment_id}", response_model=AppointmentOut)
def transition_appointment(
    appointment_id: int,
    body: AppointmentTransitionIn,
    user: User = Depends(get_current_user),
) -> AppointmentOut:
    """Move an appointment along the role-based status matrix (403/409 on abuse)."""
    appt = AppointmentController.transition(
        user.id, user.role, appointment_id, body.status, body.notes
    )
    return AppointmentOut.model_validate(appt)
