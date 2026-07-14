"""Request/response DTOs for the referral surface — boundary translation only.

No business logic, no DB access. The ``*Out`` models translate the
``sehaty.db`` ``Referral`` ORM rows and the core credit-balance projection into
the JSON contract clients consume. Code minting, referral recording and reward
settlement all live in ``ReferralController``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReferralOut(BaseModel):
    """A single referral this doctor made, as seen on the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    referred_doctor_id: int | None = None
    status: str
    reward_amount: float | None = None
    created_at: datetime


class ReferralCodeOut(BaseModel):
    """The calling doctor's own referral code."""

    code: str


class ReferralSummaryOut(BaseModel):
    """The calling doctor's referral picture: credit balance + referrals made."""

    credit_balance: float
    referrals: list[ReferralOut]
