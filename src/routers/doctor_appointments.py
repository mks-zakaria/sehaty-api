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
from sehaty.core.controllers.appointments import AppointmentController
from sehaty.db import UserRole

from deps import get_acting_doctor_id
from schemas.appointments import AppointmentOut
from schemas.doctor_appointment import AppointmentGridOut, AppointmentTransitionIn

router = APIRouter(prefix="/api/v1/doctor/appointments", tags=["doctor-appointments"])


@router.get("", response_model=list[AppointmentGridOut])
def list_doctor_appointments(
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> list[AppointmentGridOut]:
    """List the (acting) doctor's appointments with human-readable patient names."""
    rows = AppointmentController.list_for_doctor(acting_doctor_id, date_from, date_to)
    return [AppointmentGridOut.model_validate(row) for row in rows]


@router.post("/{appointment_id}/transition", response_model=AppointmentOut)
def transition_doctor_appointment(
    appointment_id: int,
    body: AppointmentTransitionIn,
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> AppointmentOut:
    """Confirm/transition an appointment on the doctor's behalf (403/409 on abuse)."""
    appt = AppointmentController.transition(
        user_id=acting_doctor_id,
        role=UserRole.DOCTOR,
        appointment_id=appointment_id,
        new_status=body.status,
        notes=body.notes,
    )
    return AppointmentOut.model_validate(appt)
