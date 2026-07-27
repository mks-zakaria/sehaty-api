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
    # Neighbourhood — the browse axis behind /{city}/{district}/{specialty}.
    district: str | None = None
    lat: float | None = None
    lng: float | None = None
    consultation_fee: float | None = None
    languages: list[str] = Field(default_factory=list)
    timezone: str | None = None
    # Public cabinet contact — drives the landing page's call / WhatsApp CTAs.
    # Distinct from the doctor's login phone, which is never published.
    phone_fixe: str | None = None
    phone_mobile: str | None = None
    whatsapp: str | None = None
    # [{"weekday": 0, "ranges": [["09:00", "12:30"], ["15:00", "19:00"]]}, ...];
    # 0=Monday, absent weekday = closed. Validated in `DoctorController`.
    opening_hours: list[dict] | None = None
    # Accepted third-party payers as slugs ("cnss", "cnops", "amo", ...).
    insurances: list[str] | None = None
    # Whether the cabinet advances the insurer's share rather than making the
    # patient pay in full and claim it back.
    tiers_payant: bool | None = None
    specialty_slugs: list[str] = Field(default_factory=list)
