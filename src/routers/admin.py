"""Admin/accreditation router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. Every route is gated to ``UserRole.ADMIN`` via
``require_roles``; business errors raised by the controller (the SehatyError
taxonomy, e.g. a missing profile -> 404) are mapped to HTTP by the global
exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.admin import AdminController
from sehaty.core.controllers.reviews import ReviewController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.admin import AdminSubscriptionOut, AdminUserOut, PendingProfessionalOut
from schemas.reviews import ReviewModerateIn, ReviewOut

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/professionals", response_model=list[PendingProfessionalOut])
def list_professionals(
    pending: bool = Query(default=True),
    _admin: User = Depends(_require_admin),
) -> list[PendingProfessionalOut]:
    """List professionals awaiting accreditation.

    ``pending`` is accepted at the boundary for the wider listing the core will
    grow; today only the pending queue is served. Parse -> controller ->
    serialize.
    """
    professionals = AdminController.list_pending_professionals()
    return [PendingProfessionalOut.model_validate(p) for p in professionals]


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


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    _admin: User = Depends(_require_admin),
) -> list[AdminUserOut]:
    """List platform users for the admin Users page, newest first.

    Optional ``role`` / ``is_active`` filters narrow the set. Parse ->
    controller -> serialize.
    """
    users = AdminController.list_users(role=role, is_active=is_active, limit=limit, offset=offset)
    return [AdminUserOut.model_validate(u) for u in users]


@router.get("/subscriptions", response_model=list[AdminSubscriptionOut])
def list_subscriptions(
    status: str | None = Query(default=None),
    limit: int = Query(default=100),
    offset: int = Query(default=0),
    _admin: User = Depends(_require_admin),
) -> list[AdminSubscriptionOut]:
    """List subscriptions for the admin Subscriptions page, newest first.

    Optional ``status`` filter narrows the set. Parse -> controller ->
    serialize.
    """
    subscriptions = AdminController.list_subscriptions(status=status, limit=limit, offset=offset)
    return [AdminSubscriptionOut.model_validate(s) for s in subscriptions]


@router.get("/reviews", response_model=list[ReviewOut])
def list_review_queue(
    _admin: User = Depends(_require_admin),
) -> list[ReviewOut]:
    """List every PENDING or FLAGGED review awaiting moderation, newest first."""
    reviews = ReviewController.list_moderation_queue()
    return [ReviewOut.model_validate(r) for r in reviews]


@router.post("/reviews/{review_id}/moderate", response_model=ReviewOut)
def moderate_review(
    review_id: int,
    body: ReviewModerateIn,
    admin: User = Depends(_require_admin),
) -> ReviewOut:
    """Publish or remove a review, recomputing the target's reputation."""
    review = ReviewController.moderate(admin.id, review_id, body.action)
    return ReviewOut.model_validate(review)
