"""Prescription-templates router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. A template is a doctor's named, reusable preset (e.g.
"Angine - adulte") that pre-builds a common freehand prescription once so it can
be dropped into a new prescription in one click. Every route is DOCTOR-scoped:
the caller's own user id is the ``doctor_id``, so a template belonging to another
doctor is a 404. Business errors (the SehatyError taxonomy —
``SehatyNotFoundError`` -> 404, ``SehatyValidationError`` -> 422) are mapped to
HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.prescription_templates import (
    PrescriptionTemplateController,
    TemplateRow,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.prescription_template import TemplateCreateIn

router = APIRouter(prefix="/api/v1/doctor/prescription-templates", tags=["prescription-templates"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=list[TemplateRow])
def list_templates(
    doctor: User = Depends(_require_doctor),
) -> list[TemplateRow]:
    """The calling doctor's templates, ordered by name (case-insensitive)."""
    return PrescriptionTemplateController.list_for(doctor.id)


@router.post("", response_model=TemplateRow, status_code=status.HTTP_201_CREATED)
def create_template(
    body: TemplateCreateIn,
    doctor: User = Depends(_require_doctor),
) -> TemplateRow:
    """Create a reusable prescription template for the calling doctor.

    ``name`` must be non-empty and ``items`` a non-empty list where each row has a
    non-empty ``drug_name`` plus required ``dosage`` and ``frequency`` (else a
    422 from the core validation).
    """
    return PrescriptionTemplateController.create(
        doctor_id=doctor.id,
        name=body.name,
        items=[i.model_dump() for i in body.items],
        notes=body.notes,
    )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    doctor: User = Depends(_require_doctor),
) -> None:
    """Delete the calling doctor's own template (404 if not theirs)."""
    PrescriptionTemplateController.delete(doctor.id, template_id)
