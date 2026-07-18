"""Doctor/assistant appointment-grid router. parse -> ONE controller call.

No SQLAlchemy here. Both handlers resolve the *effective* doctor via
``get_acting_doctor_id``: a DOCTOR acts on their own calendar, and an ASSISTANT
linked to that doctor acts on the doctor's behalf (the dependency authorizes the
link; an unlinked assistant or a patient is rejected with 403 by the global
`SehatyError` handler in `main`). The transition endpoint is how an assistant
CONFIRMS a requested appointment for the doctor — core still fires the patient
``appointment_confirmed`` notification. Business errors are mapped to HTTP by the
handler in `main`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.appointments import (
    AppointmentController,
    AppointmentGridRow,
    AppointmentRow,
)
from sehaty.db import UserRole

from deps import get_acting_doctor_id
from schemas.appointments import AppointmentTransitionIn, RescheduleIn

router = APIRouter(prefix="/api/v1/doctor/appointments", tags=["doctor-appointments"])


@router.get("", response_model=list[AppointmentGridRow])
def list_doctor_appointments(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> list[AppointmentGridRow]:
    """List the (acting) doctor's appointments with human-readable patient names."""
    return AppointmentController.list_for_doctor(acting_doctor_id, date_from, date_to)


@router.post("/{appointment_id}/transition", response_model=AppointmentRow)
def transition_doctor_appointment(
    appointment_id: int,
    body: AppointmentTransitionIn,
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> AppointmentRow:
    """Confirm/transition an appointment on the doctor's behalf (403/409 on abuse)."""
    return AppointmentController.transition(
        user_id=acting_doctor_id,
        role=UserRole.DOCTOR,
        appointment_id=appointment_id,
        new_status=body.status,
        notes=body.notes,
    )


@router.post("/{appointment_id}/reschedule", response_model=AppointmentRow)
def reschedule_doctor_appointment(
    appointment_id: int,
    body: RescheduleIn,
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> AppointmentRow:
    """Move an appointment to a different free slot on the doctor's behalf.

    Resolves the effective doctor via ``get_acting_doctor_id`` (a linked
    assistant reschedules for their doctor); a DOCTOR move preserves the current
    status. Unavailable/invalid slots are 409, an unauthorized caller is 403.
    """
    return AppointmentController.reschedule(
        user_id=acting_doctor_id,
        role=UserRole.DOCTOR,
        appointment_id=appointment_id,
        new_start_at=body.new_start_at,
        notes=body.notes,
    )
