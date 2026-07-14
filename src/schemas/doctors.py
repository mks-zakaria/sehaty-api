"""Response DTOs for the doctors surface — boundary translation only.

No business logic, no DB access. Translates a `sehaty.db.DoctorProfile` ORM
row into the JSON contract the marketplace clients consume.
"""

from pydantic import BaseModel, ConfigDict


class DoctorOut(BaseModel):
    """Public marketplace view of a verified doctor."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    slug: str
    city: str | None = None
    bio: str | None = None
    photo_url: str | None = None
    address: str | None = None
    consultation_fee: float | None = None
    verification_status: str
