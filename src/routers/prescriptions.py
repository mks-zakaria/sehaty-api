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
from sehaty.core.controllers.prescriptions import PrescriptionController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import (
    PrescriptionCreateIn,
    PrescriptionDetailOut,
    PrescriptionSummaryOut,
)

router = APIRouter(tags=["prescriptions"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_patient = require_roles(UserRole.PATIENT)


@router.post(
    "/api/v1/doctor/patients/{clinic_patient_id}/prescriptions",
    response_model=PrescriptionDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_prescription(
    clinic_patient_id: int,
    body: PrescriptionCreateIn,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetailOut:
    """Issue a prescription for one of the doctor's register patients (404 if not theirs).

    When ``practice_profile_id`` is omitted the doctor's default letterhead is
    used; ``expires_days`` defaults to the core default when omitted.
    """
    extra = {} if body.expires_days is None else {"expires_days": body.expires_days}
    detail = PrescriptionController.create(
        doctor_id=doctor.id,
        clinic_patient_id=clinic_patient_id,
        items=[i.model_dump() for i in body.items],
        practice_profile_id=body.practice_profile_id,
        appointment_id=body.appointment_id,
        notes=body.notes,
        **extra,
    )
    return PrescriptionDetailOut.model_validate(detail)


@router.get(
    "/api/v1/doctor/patients/{clinic_patient_id}/prescriptions",
    response_model=list[PrescriptionSummaryOut],
)
def list_patient_prescriptions(
    clinic_patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> list[PrescriptionSummaryOut]:
    """List a register patient's prescriptions, newest first (404 if not theirs)."""
    rows = PrescriptionController.list_for_patient(doctor.id, clinic_patient_id)
    return [PrescriptionSummaryOut.model_validate(r) for r in rows]


@router.get(
    "/api/v1/doctor/prescriptions/{prescription_id}",
    response_model=PrescriptionDetailOut,
)
def get_prescription(
    prescription_id: int,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetailOut:
    """One prescription with its items + letterhead snapshot (404 if not theirs)."""
    detail = PrescriptionController.get(doctor.id, prescription_id)
    return PrescriptionDetailOut.model_validate(detail)


@router.post(
    "/api/v1/doctor/prescriptions/{prescription_id}/cancel",
    response_model=PrescriptionDetailOut,
)
def cancel_prescription(
    prescription_id: int,
    doctor: User = Depends(_require_doctor),
) -> PrescriptionDetailOut:
    """Mark the doctor's prescription CANCELLED (404 if not theirs)."""
    detail = PrescriptionController.cancel(doctor.id, prescription_id)
    return PrescriptionDetailOut.model_validate(detail)


@router.get("/api/v1/me/prescriptions", response_model=list[PrescriptionSummaryOut])
def my_prescriptions(
    user: User = Depends(_require_patient),
) -> list[PrescriptionSummaryOut]:
    """The calling patient's OWN prescriptions across doctors, newest first."""
    rows = PrescriptionController.list_for_app_patient(user.id)
    return [PrescriptionSummaryOut.model_validate(r) for r in rows]
