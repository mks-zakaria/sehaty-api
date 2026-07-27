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

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.billing import (
    BillingController,
    PaymentRow,
    PlanRow,
    SubscriptionRow,
    SubscriptionSummary,
)
from sehaty.core.controllers.payment_tracking import (
    PaymentBoard,
    PaymentTrackingController,
)
from sehaty.db import User, UserRole

from deps import get_current_user, require_roles
from schemas.billing import (
    CashPaymentIn,
    SubscribeIn,
)

router = APIRouter(prefix="/api/v1/billing", tags=["billing"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_admin = require_roles(UserRole.ADMIN)


@router.get("/plans", response_model=list[PlanRow])
def list_plans(
    _user: User = Depends(get_current_user),
) -> list[PlanRow]:
    """List the active plan catalogue (any authenticated user)."""
    return BillingController.list_plans()


@router.get("/me", response_model=SubscriptionSummary)
def my_subscription(
    doctor: User = Depends(_require_doctor),
) -> SubscriptionSummary:
    """The calling doctor's plan, status, amount due, and period end (404 if none)."""
    return BillingController.subscription_status(doctor.id)


@router.post("/me/subscribe", response_model=SubscriptionRow)
def subscribe(
    body: SubscribeIn,
    doctor: User = Depends(_require_doctor),
) -> SubscriptionRow:
    """Start or switch the calling doctor's subscription (404 on unknown plan code)."""
    return BillingController.subscribe(doctor.id, body.plan_code)


@router.post("/admin/seed-plans")
def seed_plans(
    _admin: User = Depends(_require_admin),
) -> dict[str, int]:
    """Insert the catalogue plans; idempotent on plan code. Returns count created."""
    created = BillingController.seed_plans()
    return {"created": len(created)}


@router.post("/admin/payments", response_model=PaymentRow)
def record_cash_payment(
    body: CashPaymentIn,
    admin: User = Depends(_require_admin),
) -> PaymentRow:
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
    return payment


@router.post("/admin/dunning")
def run_dunning(
    _admin: User = Depends(_require_admin),
) -> dict[str, int]:
    """Flip subscriptions PAST_DUE for overdue OPEN invoices. Returns count flipped."""
    past_due = BillingController.run_dunning()
    return {"past_due": past_due}


@router.get("/admin/payments/board", response_model=PaymentBoard)
def payments_board(
    limit: int = Query(default=200, description="Maximum rows (1-500)."),
    _admin: User = Depends(_require_admin),
) -> PaymentBoard:
    """Who has paid, who has not, and who is about to lose their agenda.

    Ordered by urgency rather than alphabetically: a suspended cabinet is
    already losing bookings, one in grace is days away, one expiring soon is
    this week's phone call. That ordering *is* the feature.
    """
    return PaymentTrackingController.board(limit=limit)
