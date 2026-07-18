"""Diagnoses router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. A diagnosis is a condition a doctor recorded for one of
their register patients. Doctor-facing routes are DOCTOR-scoped (another
doctor's diagnosis is a 404); the ``/me`` read is PATIENT-scoped and returns the
caller's OWN diagnoses across doctors. Business errors (the SehatyError taxonomy)
are mapped to HTTP by the handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.diagnoses import DiagnosisController, DiagnosisRow
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import DiagnosisCreateIn, DiagnosisUpdateIn

router = APIRouter(tags=["diagnoses"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_patient = require_roles(UserRole.PATIENT)


@router.post(
    "/api/v1/doctor/patients/{clinic_patient_id}/diagnoses",
    response_model=DiagnosisRow,
    status_code=status.HTTP_201_CREATED,
)
def create_diagnosis(
    clinic_patient_id: int,
    body: DiagnosisCreateIn,
    doctor: User = Depends(_require_doctor),
) -> DiagnosisRow:
    """Record a diagnosis for one of the doctor's register patients (404 if not theirs)."""
    return DiagnosisController.create(
        doctor_id=doctor.id,
        clinic_patient_id=clinic_patient_id,
        label=body.label,
        icd10=body.icd10,
        notes=body.notes,
        appointment_id=body.appointment_id,
        diagnosed_at=body.diagnosed_at,
    )


@router.get(
    "/api/v1/doctor/patients/{clinic_patient_id}/diagnoses",
    response_model=list[DiagnosisRow],
)
def list_patient_diagnoses(
    clinic_patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> list[DiagnosisRow]:
    """List a register patient's diagnoses, newest first (404 if not theirs)."""
    return DiagnosisController.list_for_patient(doctor.id, clinic_patient_id)


@router.patch("/api/v1/doctor/diagnoses/{diagnosis_id}", response_model=DiagnosisRow)
def update_diagnosis(
    diagnosis_id: int,
    body: DiagnosisUpdateIn,
    doctor: User = Depends(_require_doctor),
) -> DiagnosisRow:
    """Update the doctor's own diagnosis (404 if not theirs).

    Only the fields the client sent are forwarded (``model_dump(exclude_unset=True)``).
    """
    return DiagnosisController.update(
        doctor.id, diagnosis_id, **body.model_dump(exclude_unset=True)
    )


@router.delete("/api/v1/doctor/diagnoses/{diagnosis_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_diagnosis(
    diagnosis_id: int,
    doctor: User = Depends(_require_doctor),
) -> None:
    """Delete the doctor's own diagnosis (404 if not theirs)."""
    DiagnosisController.delete(doctor.id, diagnosis_id)


@router.get("/api/v1/me/diagnoses", response_model=list[DiagnosisRow])
def my_diagnoses(
    user: User = Depends(_require_patient),
) -> list[DiagnosisRow]:
    """The calling patient's OWN diagnoses across doctors, newest first."""
    return DiagnosisController.list_for_app_patient(user.id)
