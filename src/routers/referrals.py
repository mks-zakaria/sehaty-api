"""Referral router. Body of each handler: parse -> ONE controller call ->
return.

No SQLAlchemy here. Every doctor carries a short ``referral_code`` they share;
a new doctor registering with that code is linked as a ``PENDING`` referral
(wired at ``/auth/doctor/register``) and the referrer earns a subscription
credit when the referred doctor first pays. Doctor-facing routes derive the
caller's own user id (a DOCTOR role check, like the other doctor routers).
Business errors (the SehatyError taxonomy) are mapped to HTTP by the global
exception handler in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.billing import BillingController
from sehaty.core.controllers.referral import ReferralController, ReferralRow
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.referral import ReferralCodeOut, ReferralSummaryOut

router = APIRouter(prefix="/api/v1/referrals", tags=["referrals"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("/me/code", response_model=ReferralCodeOut)
def my_code(
    doctor: User = Depends(_require_doctor),
) -> ReferralCodeOut:
    """The calling doctor's referral code, minted on first read and stable after."""
    return ReferralCodeOut(code=ReferralController.code_for(doctor.id))


@router.get("/me", response_model=ReferralSummaryOut)
def my_referrals(
    doctor: User = Depends(_require_doctor),
) -> ReferralSummaryOut:
    """The calling doctor's credit balance and the referrals they made (oldest first)."""
    referrals: list[ReferralRow] = ReferralController.list_for_referrer(doctor.id)
    return ReferralSummaryOut(
        credit_balance=BillingController.credit_balance(doctor.id),
        referrals=referrals,
    )
