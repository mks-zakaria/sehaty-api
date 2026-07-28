"""Admin/accreditation router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. Every route is gated to ``UserRole.ADMIN`` via
``require_roles``; business errors raised by the controller (the SehatyError
taxonomy, e.g. a missing profile -> 404) are mapped to HTTP by the global
exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.admin import (
    AdminController,
    PendingProfessional,
    SubscriptionRow,
    UserRow,
)
from sehaty.core.controllers.appointments import AppointmentController
from sehaty.core.controllers.prospects import ProspectBoard, ProspectController
from sehaty.core.controllers.reviews import ReviewController, ReviewRow
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.reviews import ReviewModerateIn

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_require_admin = require_roles(UserRole.ADMIN)


@router.post("/run-reminders")
def run_reminders(
    within_hours: int = Query(24, ge=1, le=168),
    _admin: User = Depends(_require_admin),
) -> dict[str, int]:
    """Send one-time patient reminders for CONFIRMED appointments starting within
    ``within_hours``. Idempotent (each appointment is reminded once) — meant to be
    triggered periodically by a scheduler/cron."""
    return {"reminded": AppointmentController.run_reminders(within_hours=within_hours)}


@router.get("/professionals", response_model=list[PendingProfessional])
def list_professionals(
    pending: bool = Query(default=True),
    _admin: User = Depends(_require_admin),
) -> list[PendingProfessional]:
    """List professionals awaiting accreditation.

    ``pending`` is accepted at the boundary for the wider listing the core will
    grow; today only the pending queue is served. Parse -> controller ->
    serialize.
    """
    return AdminController.list_pending_professionals()


@router.post("/professionals/{user_id}/accredit")
def accredit_professional(
    user_id: int,
    admin: User = Depends(_require_admin),
) -> dict[str, bool]:
    """Accredit (verify) a doctor's licence. 404 if no such profile."""
    AdminController.accredit(admin.id, user_id)
    return {"ok": True}


@router.post("/professionals/{user_id}/revoke")
def revoke_professional(
    user_id: int,
    admin: User = Depends(_require_admin),
) -> dict[str, bool]:
    """Revoke a doctor's accreditation. 404 if no such profile."""
    AdminController.revoke(admin.id, user_id)
    return {"ok": True}


@router.get("/prospects", response_model=ProspectBoard)
def prospects(
    city: str | None = Query(default=None),
    district: str | None = Query(default=None),
    onboarded: bool | None = Query(default=None),
    plan: str | None = Query(default=None, pattern="^(landing|landing_rdv)$"),
    limit: int = Query(default=500, ge=1, le=2000),
    _admin: User = Depends(_require_admin),
) -> ProspectBoard:
    """The field list: every doctor, onboarding state, tier and how to drive there."""
    return ProspectController.board(
        city=city, district=district, onboarded=onboarded, plan=plan, limit=limit
    )


@router.get("/users", response_model=list[UserRow])
def list_users(
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    _admin: User = Depends(_require_admin),
) -> list[UserRow]:
    """List platform users for the admin Users page, newest first.

    Optional ``role`` / ``is_active`` filters narrow the set. Parse ->
    controller -> serialize.
    """
    return AdminController.list_users(role=role, is_active=is_active, limit=limit, offset=offset)


@router.get("/subscriptions", response_model=list[SubscriptionRow])
def list_subscriptions(
    status: str | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    _admin: User = Depends(_require_admin),
) -> list[SubscriptionRow]:
    """List subscriptions for the admin Subscriptions page, newest first.

    Optional ``status`` filter narrows the set. Parse -> controller ->
    serialize.
    """
    return AdminController.list_subscriptions(status=status, limit=limit, offset=offset)


@router.get("/reviews", response_model=list[ReviewRow])
def list_review_queue(
    _admin: User = Depends(_require_admin),
) -> list[ReviewRow]:
    """List every PENDING or FLAGGED review awaiting moderation, newest first."""
    return ReviewController.list_moderation_queue()


@router.post("/reviews/{review_id}/moderate", response_model=ReviewRow)
def moderate_review(
    review_id: int,
    body: ReviewModerateIn,
    admin: User = Depends(_require_admin),
) -> ReviewRow:
    """Publish or remove a review, recomputing the target's reputation."""
    return ReviewController.moderate(admin.id, review_id, body.action)
