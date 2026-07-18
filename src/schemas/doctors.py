"""Request DTOs for the doctors surface — boundary translation only.

No business logic, no DB access. `*In` models parse the request body; the
response contracts are served directly from the `sehaty.core` projections
(``DoctorView`` / ``DoctorSearchResult`` / ``SpecialtyView``).
"""

from pydantic import BaseModel, Field


class DoctorProfileIn(BaseModel):
    """Doctor's self-service profile upsert (the `PUT /me/profile` body).

    Everything but `full_name` is optional; `lat`/`lng` are only persisted when
    both are supplied. Maps one-to-one onto `DoctorController.upsert_profile`
    keyword arguments via `model_dump()`.
    """

    full_name: str
    bio: str | None = None
    photo_url: str | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    consultation_fee: float | None = None
    languages: list[str] = Field(default_factory=list)
    timezone: str | None = None
    specialty_slugs: list[str] = Field(default_factory=list)
