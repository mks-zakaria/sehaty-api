"""Inbound request DTOs for the pharmacy surface — boundary translation only.

Responses are served directly from the core projections
(``PharmacyPrescriptionView`` / ``DispenseRow``).
"""

from pydantic import BaseModel


class DispenseLineIn(BaseModel):
    """One line of a dispense: how much of a prescription item to hand over."""

    prescription_item_id: int
    quantity: int


class DispenseIn(BaseModel):
    """Record a dispense against a prescription looked up by its ``code``."""

    code: str
    lines: list[DispenseLineIn]
    notes: str | None = None


class StockIn(BaseModel):
    """Create or update a pharmacy's stock for one catalogue medication."""

    medication_id: int
    quantity: int
    price: float | None = None
    low_threshold: int = 10


class ProductIn(BaseModel):
    """Register (or update, by barcode) an over-the-counter product."""

    barcode: str
    name: str
    kind: str  # "MEDICINE" | "COSMETIC"
    medication_id: int | None = None
    price: float | None = None
    quantity: int = 0
    low_threshold: int = 10


class RestockIn(BaseModel):
    """Add received stock to a product."""

    product_id: int
    add: int


class SaleLineIn(BaseModel):
    """One basket line — resolved by product_id or scanned barcode."""

    product_id: int | None = None
    barcode: str | None = None
    quantity: int


class SaleIn(BaseModel):
    """Record a sale of a scanned basket."""

    lines: list[SaleLineIn]
