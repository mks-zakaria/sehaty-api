"""Response DTOs for the admin reporting surface — boundary translation.

No business logic, no DB access. These ``*Out`` models translate the frozen
projection dataclasses returned by ``sehaty.core``'s ``ReportingController``
(``PlatformKpis``, ``RevenueSummary`` / ``MonthRevenue``) into the JSON contract
the admin dashboard consumes. The year-end accounting trail is a CSV stream, a
transport concern shaped in the router — it has no ``*Out`` model here.
"""

from pydantic import BaseModel, ConfigDict


class KpisOut(BaseModel):
    """The operational marketplace snapshot (core ``PlatformKpis``)."""

    model_config = ConfigDict(from_attributes=True)

    doctors_total: int
    doctors_verified: int
    patients_total: int
    appointments_by_status: dict[str, int]
    reviews_published: int
    referrals_rewarded: int
    active_subscriptions: int


class MonthRevenueOut(BaseModel):
    """Cash collected in one calendar month (core ``MonthRevenue``)."""

    model_config = ConfigDict(from_attributes=True)

    month: int
    collected: float
    payments: int


class RevenueSummaryOut(BaseModel):
    """A fiscal year's cash picture (core ``RevenueSummary``)."""

    model_config = ConfigDict(from_attributes=True)

    year: int
    total_collected: float
    currency: str
    by_month: list[MonthRevenueOut]
    active_subscriptions: int
    mrr: float
