"""Request/response DTOs for the cash-billing surface — boundary translation.

No business logic, no DB access. ``*In`` models parse the request body; the
``*Out`` models translate the ``sehaty.db`` billing ORM rows into the JSON
contract clients consume.
Plan catalogue, subscription lifecycle, cash-payment idempotency and the
dunning sweep all live in ``BillingController``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sehaty.db import SubscriptionStatus


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


class PlanOut(BaseModel):
    """A catalogue plan as seen on the wire."""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    price_month: float
    currency: str


class SubscriptionOut(BaseModel):
    """A doctor's subscription row as seen on the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    plan_id: int
    status: SubscriptionStatus
    current_period_end: datetime


class PaymentOut(BaseModel):
    """A recorded cash payment as seen on the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    invoice_id: int
    amount: float
    method: str
    paid_at: datetime
