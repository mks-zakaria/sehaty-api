"""Consultation-flow router: check-in -> start -> complete, plus the doctor queue.

No SQLAlchemy here. The secretary checks a patient in against an open cabinet
session (notifying the acting doctor); the acting doctor then starts and completes
the consultation, recording the encounter. Business errors map to HTTP in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.appointments import (
    AppointmentController,
    AppointmentRow,
    ConsultationRow,
    WaitingPatientRow,
)
from sehaty.core.controllers.cabinet import CabinetController, CabinetRow, CabinetSessionRow
from sehaty.db import User, UserRole

from deps import get_acting_doctor_id, require_roles
from schemas.cabinet import CheckInIn, CompleteConsultationIn

router = APIRouter(prefix="/api/v1/consultations", tags=["consultations"])

_require_doctor = require_roles(UserRole.DOCTOR)
# The front desk: the doctor themselves or their secretary (assistant).
_require_desk = require_roles(UserRole.DOCTOR, UserRole.ASSISTANT)


@router.get("/active-session", response_model=CabinetSessionRow | None)
def active_session(
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> CabinetSessionRow | None:
    """The open cabinet session for the acting doctor (owner or a secretary's doctor).

    Lets a secretary discover the online session so they can check patients in;
    returns null when nobody is online.
    """
    return CabinetController.active_session_for_owner(acting_doctor_id)


@router.get("/cabinets", response_model=list[CabinetRow])
def desk_cabinets(
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> list[CabinetRow]:
    """The acting doctor's cabinets (desk-accessible).

    Lets a secretary read the waiting-room count / alert threshold and set the
    count even when nobody is online yet (e.g. first thing in the morning).
    """
    return CabinetController.list_for_owner(acting_doctor_id)


@router.get("/queue", response_model=list[WaitingPatientRow])
def waiting_queue(user: User = Depends(_require_doctor)) -> list[WaitingPatientRow]:
    """The calling doctor's live queue of checked-in patients, with their profiles."""
    return AppointmentController.waiting_queue(user.id)


@router.post("/{appointment_id}/check-in", response_model=AppointmentRow)
def check_in(
    appointment_id: int, body: CheckInIn, user: User = Depends(_require_desk)
) -> AppointmentRow:
    """Check a patient in against an open session; notifies the acting doctor."""
    return AppointmentController.check_in(appointment_id, body.cabinet_session_id)


@router.post("/{appointment_id}/start", response_model=ConsultationRow)
def start_consultation(
    appointment_id: int, user: User = Depends(_require_doctor)
) -> ConsultationRow:
    """The acting doctor starts the consultation (records the start time)."""
    return AppointmentController.start_consultation(appointment_id, user.id)


@router.post("/{appointment_id}/complete", response_model=ConsultationRow)
def complete_consultation(
    appointment_id: int,
    body: CompleteConsultationIn,
    user: User = Depends(_require_doctor),
) -> ConsultationRow:
    """The acting doctor finishes and records the consultation (encounter data)."""
    return AppointmentController.complete_consultation(
        appointment_id,
        user.id,
        chief_complaint=body.chief_complaint,
        symptoms=body.symptoms,
        vitals=body.vitals,
        exam_notes=body.exam_notes,
    )
