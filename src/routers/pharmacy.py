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
from sehaty.core.controllers.products import (
    ProductController,
    ProductRow,
    SaleController,
    SaleRow,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.pharmacy import DispenseIn, ProductIn, RestockIn, SaleIn, StockIn

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


# --- Point-of-sale: products + sales -------------------------------------


@router.get("/products", response_model=list[ProductRow])
def list_products(
    search: str | None = Query(default=None),
    low: bool = Query(default=False),
    user: User = Depends(_require_pharmacy),
) -> list[ProductRow]:
    """The pharmacy's over-the-counter catalogue (filter by name/barcode, low-only)."""
    return ProductController.list_products(user.id, search=search, low_only=low)


@router.get("/products/{barcode}", response_model=ProductRow)
def lookup_product(barcode: str, user: User = Depends(_require_pharmacy)) -> ProductRow:
    """Scan a barcode to see a product's full info (404 if unknown)."""
    return ProductController.lookup(user.id, barcode)


@router.post("/products", response_model=ProductRow)
def register_product(body: ProductIn, user: User = Depends(_require_pharmacy)) -> ProductRow:
    """Register (or update, by barcode) a MEDICINE or COSMETIC product."""
    return ProductController.register(
        user.id,
        body.barcode,
        body.name,
        body.kind,
        medication_id=body.medication_id,
        price=body.price,
        quantity=body.quantity,
        low_threshold=body.low_threshold,
    )


@router.post("/products/restock", response_model=ProductRow)
def restock_product(body: RestockIn, user: User = Depends(_require_pharmacy)) -> ProductRow:
    """Add received stock to a product."""
    return ProductController.restock(user.id, body.product_id, body.add)


@router.get("/sales", response_model=list[SaleRow])
def list_sales(
    limit: int = Query(default=50, le=200), user: User = Depends(_require_pharmacy)
) -> list[SaleRow]:
    """Recent sales (newest first) — the sales history."""
    return SaleController.list_sales(user.id, limit=limit)


@router.post("/sales", response_model=SaleRow)
def record_sale(body: SaleIn, user: User = Depends(_require_pharmacy)) -> SaleRow:
    """Record a sale of a scanned basket (409 if a product is out of stock)."""
    return SaleController.sell(user.id, [line.model_dump() for line in body.lines])
