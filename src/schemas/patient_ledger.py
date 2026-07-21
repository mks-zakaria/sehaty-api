"""Request DTOs for the patient debt-ledger surface — boundary only.

No business logic, no DB access. The ``*In`` models parse the request bodies;
responses are served directly from the core ``PatientLedgerController``
projections (``ChargeRow``, ``PatientLedgerSummary``, ``DebtorRow``), which are
pydantic models used as FastAPI ``response_model`` without a parallel ``*Out``
mirror. The ledger itself — doctor-scoped charges collected in instalments with
a derived balance — lives in ``PatientLedgerController``.
"""

from datetime import datetime

from pydantic import BaseModel


class ChargeCreateIn(BaseModel):
    """A treatment charge (the ``POST /patients/{id}/ledger/charges`` body)."""

    label: str
    total_amount: float
    currency: str = "MAD"
    note: str | None = None
    # Optional same-visit down payment, recorded as a CASH payment.
    initial_payment: float | None = None


class PaymentCreateIn(BaseModel):
    """An instalment (the ``POST /ledger/charges/{id}/payments`` body)."""

    amount: float
    method: str = "CASH"
    note: str | None = None
    # Defaults to "now" server-side when omitted.
    paid_at: datetime | None = None
