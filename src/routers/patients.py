"""Patient-register router. Body of each handler: parse -> ONE controller call
-> return.

No SQLAlchemy here. A doctor keeps a register of ALL their patients — app users
who booked (a booking auto-creates the register row) and walk-in/phone patients
with no account, added straight from the grid — each row carrying denormalised
contact + demographic fields plus live-aggregated visit stats. Every route is
DOCTOR-scoped: the caller's own user id is the ``doctor_id`` (and, on create,
the ``created_by``), so a register row belonging to another doctor is a 404.
Business errors (the SehatyError taxonomy — ``SehatyNotFoundError`` -> 404,
``SehatyValidationError`` -> 422) are mapped to HTTP by the global exception
handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.patients import (
    PatientDetail,
    PatientRegisterController,
    PatientRow,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.patient import PatientCreateIn, PatientUpdateIn

router = APIRouter(prefix="/api/v1/doctor/patients", tags=["patients"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=list[PatientRow])
def list_patients(
    search: str | None = None,
    sort: str = "name",
    limit: int = 50,
    offset: int = 0,
    doctor: User = Depends(_require_doctor),
) -> list[PatientRow]:
    """The calling doctor's register with live visit stats.

    ``search`` matches name/phone/email (case-insensitive contains); ``sort`` is
    one of ``name`` (default), ``recent``, ``visits`` or ``upcoming`` (an unknown
    value is a 422).
    """
    return PatientRegisterController.list_patients(
        doctor.id, search=search, sort=sort, limit=limit, offset=offset
    )


@router.get("/{patient_id}", response_model=PatientDetail)
def get_patient(
    patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> PatientDetail:
    """One register row with demographics + full visit history (404 if not the doctor's)."""
    return PatientRegisterController.get_patient(doctor.id, patient_id)


@router.post("", response_model=PatientRow, status_code=status.HTTP_201_CREATED)
def add_patient(
    body: PatientCreateIn,
    doctor: User = Depends(_require_doctor),
) -> PatientRow:
    """Add a walk-in / manually-entered patient (``user_id`` NULL, zeroed aggregates)."""
    return PatientRegisterController.add_patient(
        doctor_id=doctor.id,
        created_by=doctor.id,
        full_name=body.full_name,
        phone=body.phone,
        email=body.email,
        sex=body.sex,
        birth_year=body.birth_year,
        notes=body.notes,
        tags=body.tags,
    )


@router.patch("/{patient_id}", response_model=PatientDetail)
def update_patient(
    patient_id: int,
    body: PatientUpdateIn,
    doctor: User = Depends(_require_doctor),
) -> PatientDetail:
    """Update demographics on the doctor's own register row (404 if not theirs).

    Only the fields the client actually sent are forwarded
    (``model_dump(exclude_unset=True)``), so an omitted field is left untouched.
    """
    return PatientRegisterController.update_patient(
        doctor.id, patient_id, **body.model_dump(exclude_unset=True)
    )
