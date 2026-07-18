"""Appointments router. Body of each handler: parse -> ONE controller call.

No SQLAlchemy here. Patients book concrete slots; the owning patient/doctor
then drive the appointment through the role-based status matrix. Business errors
(the SehatyError taxonomy) are mapped to HTTP by the handler in `main`.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.appointments import (
    AppointmentController,
    AppointmentRow,
    PatientAppointmentRow,
)
from sehaty.db import User, UserRole

from deps import get_current_user, require_roles
from schemas.appointments import (
    AppointmentIn,
    AppointmentTransitionIn,
    RescheduleIn,
)

router = APIRouter(prefix="/api/v1/appointments", tags=["appointments"])

_require_patient = require_roles(UserRole.PATIENT)


@router.post("", response_model=AppointmentRow, status_code=status.HTTP_201_CREATED)
def book_appointment(
    body: AppointmentIn,
    user: User = Depends(_require_patient),
) -> AppointmentRow:
    """Book a free slot as the calling patient (409 if it is not bookable)."""
    return AppointmentController.book(user.id, body.doctor_id, body.start_at, body.reason)


@router.get("", response_model=list[PatientAppointmentRow | AppointmentRow])
def list_appointments(
    user: User = Depends(get_current_user),
) -> list[PatientAppointmentRow] | list[AppointmentRow]:
    """List the caller's appointments (patient: booked; doctor: on their calendar).

    A PATIENT gets the enriched view carrying the resolved ``doctor_name`` (the
    ``PatientAppointmentRow`` projection); every other role keeps the plain
    ``AppointmentRow`` (with ``patient_id``/``doctor_id``) as before.
    """
    if user.role == UserRole.PATIENT:
        return AppointmentController.list_for_patient_view(user.id)
    return AppointmentController.list_for(user.id, user.role)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentRow)
def reschedule_appointment(
    appointment_id: int,
    body: RescheduleIn,
    user: User = Depends(_require_patient),
) -> AppointmentRow:
    """Move the calling patient's own appointment to a different free slot.

    Only the owning patient may act (403 otherwise); the move resets the status
    to REQUESTED and validates the new slot (409 if it is not bookable).
    """
    return AppointmentController.reschedule(
        user.id, UserRole.PATIENT, appointment_id, body.new_start_at, body.notes
    )


@router.patch("/{appointment_id}", response_model=AppointmentRow)
def transition_appointment(
    appointment_id: int,
    body: AppointmentTransitionIn,
    user: User = Depends(get_current_user),
) -> AppointmentRow:
    """Move an appointment along the role-based status matrix (403/409 on abuse)."""
    return AppointmentController.transition(
        user.id, user.role, appointment_id, body.status, body.notes
    )
