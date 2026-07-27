"""Doctor analytics router. Body: parse -> ONE controller call -> return.

No SQLAlchemy here. Gated to ``UserRole.DOCTOR``; the caller's own user id is
the ``doctor_id``. Business errors map to HTTP via the global handler in
``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.analytics import DoctorAnalytics, DoctorAnalyticsController
from sehaty.db import User, UserRole

from deps import require_roles

router = APIRouter(prefix="/api/v1/doctor/analytics", tags=["analytics"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=DoctorAnalytics)
def doctor_analytics(months: int = 6, doctor: User = Depends(_require_doctor)) -> DoctorAnalytics:
    """The calling doctor's practice-insights trend over the last ``months``."""
    return DoctorAnalyticsController.doctor_analytics(doctor.id, months=months)
