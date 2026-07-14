"""Cash-billing router. Body of each handler: parse -> ONE controller call ->
return.

No SQLAlchemy here. Sehaty never touches an online payment rail — it only
*tracks* the cash a doctor hands over at the desk: recording a receipt is
idempotent in core (replaying the same receipt number is a no-op, never a
double charge). Doctor-facing routes derive the caller's own user id (a DOCTOR
role check, like the other doctor routers); admin-facing routes are gated to
``UserRole.ADMIN`` via ``require_roles``. Business errors (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in ``main``.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sehaty.core.controllers.billing import BillingController
from sehaty.db import User, UserRole

from deps import get_current_user, require_roles
from schemas.billing import (
    CashPaymentIn,
    PaymentOut,
    PlanOut,
    SubscribeIn,
    SubscriptionOut,
    SubscriptionSummaryOut,
)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_admin = require_roles(UserRole.ADMIN)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    _user: User = Depends(get_current_user),
) -> list[PlanOut]:
    """List the active plan catalogue (any authenticated user)."""
    plans = BillingController.list_plans()
    return [PlanOut.model_validate(p) for p in plans]


@router.get("/me", response_model=SubscriptionSummaryOut)
def my_subscription(
    doctor: User = Depends(_require_doctor),
) -> SubscriptionSummaryOut:
    """The calling doctor's plan, status, amount due, and period end (404 if none)."""
    summary = BillingController.subscription_status(doctor.id)
    return SubscriptionSummaryOut.model_validate(summary)


@router.post("/me/subscribe", response_model=SubscriptionOut)
def subscribe(
    body: SubscribeIn,
    doctor: User = Depends(_require_doctor),
) -> SubscriptionOut:
    """Start or switch the calling doctor's subscription (404 on unknown plan code)."""
    subscription = BillingController.subscribe(doctor.id, body.plan_code)
    return SubscriptionOut.model_validate(subscription)


@router.post("/admin/seed-plans")
def seed_plans(
    _admin: User = Depends(_require_admin),
) -> dict[str, int]:
    """Insert the catalogue plans; idempotent on plan code. Returns count created."""
    created = BillingController.seed_plans()
    return {"created": len(created)}


@router.post("/admin/payments", response_model=PaymentOut)
def record_cash_payment(
    body: CashPaymentIn,
    admin: User = Depends(_require_admin),
) -> PaymentOut:
    """Record cash against an invoice (ADMIN only); idempotent per receipt number.

    ``paid_at`` defaults to now (server-side) when omitted. 404 on a missing
    invoice; replaying a known receipt returns the existing payment untouched.
    """
    paid_at = body.paid_at if body.paid_at is not None else datetime.now(UTC)
    payment = BillingController.record_cash_payment(
        admin_id=admin.id,
        invoice_id=body.invoice_id,
        amount=body.amount,
        receipt_no=body.receipt_no,
        paid_at=paid_at,
    )
    return PaymentOut.model_validate(payment)


@router.post("/admin/dunning")
def run_dunning(
    _admin: User = Depends(_require_admin),
) -> dict[str, int]:
    """Flip subscriptions PAST_DUE for overdue OPEN invoices. Returns count flipped."""
    past_due = BillingController.run_dunning()
    return {"past_due": past_due}
