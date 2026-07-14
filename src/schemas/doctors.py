"""Request/response DTOs for the doctors surface — boundary translation only.

No business logic, no DB access. `*In` models parse the request body; `*Out`
models translate a `sehaty.core` view (a frozen dataclass) or a
`sehaty.db.DoctorProfile` ORM row into the JSON contract clients consume.
"""

from pydantic import BaseModel, ConfigDict, Field


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
    specialty_slugs: list[str] = Field(default_factory=list)


class SpecialtyRefOut(BaseModel):
    """One specialty a doctor is tagged with (localized names, no id)."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    name_en: str
    name_fr: str
    name_ar: str


class DoctorPublicOut(BaseModel):
    """Public doctor page — mirrors `sehaty.core`'s `DoctorView`.

    Coordinates arrive as plain `lat`/`lng` floats (the raw PostGIS geography is
    never exposed); only VERIFIED doctors are ever serialized here.
    """

    model_config = ConfigDict(from_attributes=True)

    slug: str
    full_name: str
    bio: str | None = None
    photo_url: str | None = None
    address: str | None = None
    city: str | None = None
    lat: float | None = None
    lng: float | None = None
    consultation_fee: float | None = None
    languages: list[str]
    verification_status: str
    specialties: list[SpecialtyRefOut]


class SpecialtyOut(BaseModel):
    """One row of the medical-specialties catalogue."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name_en: str
    name_fr: str
    name_ar: str
