"""Prescriptions router. Body of each handler: parse -> ONE controller call ->
return.

No SQLAlchemy here. A doctor issues a prescription for any patient in their
register (including walk-ins); each is minted with a public code + QR token and
issued under a letterhead so the printable document survives the profile's
removal. Doctor-facing routes are DOCTOR-scoped (the caller's own user id is the
``doctor_id``, so another doctor's prescription is a 404); the ``/me`` read is
PATIENT-scoped and returns the caller's OWN prescriptions across doctors.
Business errors (the SehatyError taxonomy) are mapped to HTTP by the handler in
``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.prescriptions import (
    PrescriptionController,
    PrescriptionDetail,
    PrescriptionSummary,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import PrescriptionCreateIn

router = APIRouter(tags=["prescriptions"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_patient = require_roles(UserRole.PATIENT)


@router.post(
    "/api/v1/doctor/patients/{clinic_patient_id}/prescriptions",
    response_model=PrescriptionDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_prescription(
    clinic_patient_id: int,
    body: PrescriptionCreateIn,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetail:
    """Issue a prescription for one of the doctor's register patients (404 if not theirs).

    When ``practice_profile_id`` is omitted the doctor's default letterhead is
    used; ``expires_days`` defaults to the core default when omitted.
    """
    extra = {} if body.expires_days is None else {"expires_days": body.expires_days}
    return PrescriptionController.create(
        doctor_id=doctor.id,
        clinic_patient_id=clinic_patient_id,
        items=[i.model_dump() for i in body.items],
        practice_profile_id=body.practice_profile_id,
        appointment_id=body.appointment_id,
        notes=body.notes,
        **extra,
    )


@router.get(
    "/api/v1/doctor/patients/{clinic_patient_id}/prescriptions",
    response_model=list[PrescriptionSummary],
)
def list_patient_prescriptions(
    clinic_patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> list[PrescriptionSummary]:
    """List a register patient's prescriptions, newest first (404 if not theirs)."""
    return PrescriptionController.list_for_patient(doctor.id, clinic_patient_id)


@router.get(
    "/api/v1/doctor/prescriptions/{prescription_id}",
    response_model=PrescriptionDetail,
)
def get_prescription(
    prescription_id: int,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetail:
    """One prescription with its items + letterhead snapshot (404 if not theirs)."""
    return PrescriptionController.get(doctor.id, prescription_id)


@router.post(
    "/api/v1/doctor/prescriptions/{prescription_id}/cancel",
    response_model=PrescriptionDetail,
)
def cancel_prescription(
    prescription_id: int,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetail:
    """Mark the doctor's prescription CANCELLED (404 if not theirs)."""
    return PrescriptionController.cancel(doctor.id, prescription_id)


@router.get("/api/v1/me/prescriptions", response_model=list[PrescriptionSummary])
def my_prescriptions(
    user: User = Depends(_require_patient),
) -> list[PrescriptionSummary]:
    """The calling patient's OWN prescriptions across doctors, newest first."""
    return PrescriptionController.list_for_app_patient(user.id)


@router.get("/api/v1/me/prescriptions/{prescription_id}", response_model=PrescriptionDetail)
def my_prescription_detail(
    prescription_id: int,
    user: User = Depends(_require_patient),
) -> PrescriptionDetail:
    """One of the calling patient's OWN prescriptions with items + letterhead.

    403 if the prescription belongs to another patient; 404 if it does not exist
    (both mapped from the SehatyError taxonomy by the global handler in ``main``).
    """
    return PrescriptionController.get_for_app_patient(user.id, prescription_id)
