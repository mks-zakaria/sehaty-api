"""Pharmacy router: look up a prescription by code and dispense its items.

No SQLAlchemy here. Gated to ``UserRole.PHARMACY``; the acting pharmacy is the
token's user. Business errors map to HTTP via the global handler in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.pharmacy import (
    DispenseRow,
    PharmacyController,
    PharmacyPrescriptionView,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.pharmacy import DispenseIn

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])

_require_pharmacy = require_roles(UserRole.PHARMACY)


@router.get("/prescriptions/{code}", response_model=PharmacyPrescriptionView)
def lookup_prescription(
    code: str, _user: User = Depends(_require_pharmacy)
) -> PharmacyPrescriptionView:
    """Show a prescription's outstanding lines for dispensing (404 if unknown)."""
    return PharmacyController.lookup(code)


@router.post("/dispenses", response_model=DispenseRow)
def record_dispense(body: DispenseIn, user: User = Depends(_require_pharmacy)) -> DispenseRow:
    """Record a dispense against a prescription (409 on over-dispense/expired/cancelled)."""
    return PharmacyController.dispense(
        user.id, body.code, [line.model_dump() for line in body.lines], notes=body.notes
    )
