"""Request/response DTOs for the admin/accreditation surface.

No business logic, no DB access. Handlers call a single ``AdminController``
method and serialise the result back out. ``PendingProfessionalOut`` maps the
core ``PendingProfessional`` dataclass (from_attributes) onto the wire.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PendingProfessionalOut(BaseModel):
    """A doctor awaiting accreditation, as returned to an admin."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    speciality: str | None = None
    license_no: str
    city: str | None = None
    email: str


class AdminUserOut(BaseModel):
    """One row of the admin Users page (maps the core ``UserRow`` dataclass)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    phone: str | None = None
    role: str
    is_active: bool
    full_name: str | None = None
    created_at: datetime


class AdminSubscriptionOut(BaseModel):
    """One row of the admin Subscriptions page (maps ``SubscriptionRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
    doctor_name: str | None = None
    plan_code: str
    plan_name: str
    price_month: float
    currency: str
    status: str
    current_period_end: datetime
