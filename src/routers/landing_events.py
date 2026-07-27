"""Landing-analytics router: ingest public-page interactions, report per doctor.

``POST /events`` is called from the public landing site by an unauthenticated
beacon, so it is deliberately forgiving: an unknown slug or event type returns
``{"recorded": false}`` with 202 rather than an error status. A 4xx here would
show up as a console error on a doctor's public page and help nobody.

``GET /me/stats`` is the doctor-facing side — the numbers behind the upsell.
"""

from fastapi import APIRouter, Depends, Query, status
from sehaty.core.controllers.landing_analytics import (
    EventCounts,
    LandingAnalyticsController,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.landing_events import LandingEventIn, LandingEventOut

router = APIRouter(prefix="/api/v1", tags=["landing-analytics"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.post("/events", response_model=LandingEventOut, status_code=status.HTTP_202_ACCEPTED)
def record_event(body: LandingEventIn) -> LandingEventOut:
    """Record one public-page interaction (fire-and-forget, unauthenticated).

    Accepts and ignores anything it cannot attribute — see the module docstring.
    """
    recorded = LandingAnalyticsController.record(
        doctor_slug=body.slug,
        event_type=body.type,
        source=body.source,
    )
    return LandingEventOut(recorded=recorded)


@router.get("/doctors/me/stats", response_model=EventCounts)
def my_landing_stats(
    days: int = Query(default=30, description="Window length in days (1-366)."),
    user: User = Depends(_require_doctor),
) -> EventCounts:
    """The caller's own landing-page activity over the last ``days``."""
    return LandingAnalyticsController.counts_for_doctor(user.id, days=days)
