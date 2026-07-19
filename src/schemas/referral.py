"""Request/response DTOs for the referral surface — boundary translation only.

No business logic, no DB access. The remaining ``*Out`` models are deferred
scalar/composite wrappers over the core credit-balance projection and the
``ReferralRow`` core projection. The single-referral view is owned by
``ReferralController.list_for_referrer`` (returning ``ReferralRow``), which the
transport layer serialises directly. Code minting, referral recording and
reward settlement all live in ``ReferralController``.
"""

from pydantic import BaseModel
from sehaty.core.controllers.referral import ReferralRow


class ReferralCodeOut(BaseModel):
    """The calling doctor's own referral code."""

    code: str


class ReferralSummaryOut(BaseModel):
    """The calling doctor's referral picture: credit balance + referrals made."""

    credit_balance: float
    referrals: list[ReferralRow]
