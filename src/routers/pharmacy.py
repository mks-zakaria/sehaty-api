"""Pharmacy router: look up a prescription by code and dispense its items.

No SQLAlchemy here. Gated to ``UserRole.PHARMACY``; the acting pharmacy is the
token's user. Business errors map to HTTP via the global handler in ``main``.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.pharmacy import (
    DispenseRow,
    MedicationRow,
    PharmacyController,
    PharmacyPrescriptionView,
    StockRow,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.pharmacy import DispenseIn, StockIn

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


@router.get("/stock", response_model=list[StockRow])
def list_stock(
    search: str | None = Query(default=None),
    low: bool = Query(default=False),
    user: User = Depends(_require_pharmacy),
) -> list[StockRow]:
    """The pharmacy's stock, optionally filtered by medication name / low-only."""
    return PharmacyController.list_stock(user.id, search=search, low_only=low)


@router.post("/stock", response_model=StockRow)
def save_stock(body: StockIn, user: User = Depends(_require_pharmacy)) -> StockRow:
    """Create or update the pharmacy's stock for a medication."""
    return PharmacyController.save_stock(
        user.id,
        body.medication_id,
        body.quantity,
        price=body.price,
        low_threshold=body.low_threshold,
    )


@router.get("/medications", response_model=list[MedicationRow])
def search_medications(
    q: str = Query(default=""), _user: User = Depends(_require_pharmacy)
) -> list[MedicationRow]:
    """Search the medication catalogue by INN / brand name (for the add-stock picker)."""
    return PharmacyController.search_medications(q)
