"""Doctor dashboard router. Body: parse -> ONE controller call -> return.

No SQLAlchemy here. Gated to ``UserRole.DOCTOR``; the caller's own user id is
the ``doctor_id``. Business errors map to HTTP via the global handler in
``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.dashboard import DashboardController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.dashboard import DoctorDashboardOut

router = APIRouter(prefix="/api/v1/doctor/dashboard", tags=["dashboard"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=DoctorDashboardOut)
def doctor_dashboard(doctor: User = Depends(_require_doctor)) -> DoctorDashboardOut:
    """The calling doctor's home stats: today, to-confirm, upcoming, patients, next."""
    return DoctorDashboardOut.model_validate(DashboardController.doctor_stats(doctor.id))
