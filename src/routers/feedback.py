"""Treatment-feedback router. Body of each handler: parse -> ONE controller call
-> return.

No SQLAlchemy here. A patient reports whether a prescription/diagnosis/visit
left them BETTER / SAME / WORSE — but only on their OWN records: ``leave``
resolves the target's owning register row and requires it to link the caller
(else a 403). The doctor-facing read is DOCTOR-scoped (another doctor's register
patient is a 404). Business errors (the SehatyError taxonomy) are mapped to HTTP
by the handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.feedback import TreatmentFeedbackController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import FeedbackIn, FeedbackOut

router = APIRouter(tags=["feedback"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_patient = require_roles(UserRole.PATIENT)


@router.post("/api/v1/me/feedback", response_model=FeedbackOut, status_code=status.HTTP_201_CREATED)
def leave_feedback(
    body: FeedbackIn,
    user: User = Depends(_require_patient),
) -> FeedbackOut:
    """Leave (or update) the caller's outcome on one of their OWN records.

    A target the caller does not own is a 403; an unknown target is a 404.
    """
    row = TreatmentFeedbackController.leave(
        author_user_id=user.id,
        target_type=body.target_type,
        target_id=body.target_id,
        outcome=body.outcome,
        comment=body.comment,
    )
    return FeedbackOut.model_validate(row)


@router.get(
    "/api/v1/doctor/patients/{clinic_patient_id}/feedback",
    response_model=list[FeedbackOut],
)
def list_patient_feedback(
    clinic_patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> list[FeedbackOut]:
    """List all feedback for one of the doctor's register patients (404 if not theirs)."""
    rows = TreatmentFeedbackController.list_for_patient(doctor.id, clinic_patient_id)
    return [FeedbackOut.model_validate(r) for r in rows]
