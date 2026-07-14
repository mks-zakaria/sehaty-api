"""Admin/accreditation router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. Every route is gated to ``UserRole.ADMIN`` via
``require_roles``; business errors raised by the controller (the SehatyError
taxonomy, e.g. a missing profile -> 404) are mapped to HTTP by the global
exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.admin import AdminController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.admin import PendingProfessionalOut

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
