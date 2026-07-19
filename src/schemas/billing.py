"""Request/response DTOs for the cash-billing surface — boundary translation.

No business logic, no DB access. ``*In`` models parse the request body; the
response projections (``PlanRow`` / ``SubscriptionRow`` / ``PaymentRow``) are
owned by ``BillingController`` and serialised directly by the router.
Plan catalogue, subscription lifecycle, cash-payment idempotency and the
dunning sweep all live in ``BillingController``.
"""

from datetime import datetime

from pydantic import BaseModel


class SubscribeIn(BaseModel):
    """A doctor's plan choice (the ``POST /billing/me/subscribe`` body)."""

    plan_code: str


class CashPaymentIn(BaseModel):
    """Cash handed over at the desk (the ``POST /billing/admin/payments`` body).

    ``paid_at`` is optional; the router defaults it to ``datetime.now(UTC)``.
    """

    invoice_id: int
    amount: float
    receipt_no: str
    paid_at: datetime | None = None
