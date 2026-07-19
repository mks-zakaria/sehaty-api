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
