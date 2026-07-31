"""Admin DTOs for per-doctor landing-page configuration.

Template choice is a staff action taken at onboarding, not something a doctor
picks — so these live behind the admin guard rather than on `/doctors/me`.
"""

from pydantic import BaseModel, Field


class ServiceIn(BaseModel):
    """One act, with an optional published price."""

    label: str
    # Optional on purpose: plenty of doctors will not publish a price, and an
    # invented figure on a public page is worse than no figure.
    price: float | None = None


class FaqIn(BaseModel):
    q: str
    a: str


class LandingConfigIn(BaseModel):
    """Partial update — every field omitted is left untouched."""

    template: str | None = Field(
        default=None,
        description="Template key; omit to keep the specialty default.",
    )
    layout: str | None = Field(
        default=None,
        description="Design key (classic, editorial, compact, clinique); omit to keep the current.",
    )
    accent: str | None = Field(default=None, description="Hex colour, e.g. #2b73b3.")
    section_order: list[str] | None = None
    services: list[ServiceIn] | None = None
    equipment: list[str] | None = None
    faq: list[FaqIn] | None = None
    tagline: str | None = None


class PersonalizedIn(BaseModel):
    """Turn the paid personalisation on or off — recorded when the pack sells."""

    enabled: bool


class DoctorProfilePatchIn(BaseModel):
    """Partial profile edit from the console — omitted fields stay untouched.

    Distinct from `DoctorProfileIn`, which is the doctor's own form and posts
    every field. Staff send only what they collected during the visit, so a
    replace-everything body would wipe values the operator never saw.
    """

    full_name: str | None = None
    bio: str | None = None
    photo_url: str | None = None
    address: str | None = None
    city: str | None = None
    district: str | None = None
    lat: float | None = None
    lng: float | None = None
    consultation_fee: float | None = None
    languages: list[str] | None = None
    timezone: str | None = None
    phone_fixe: str | None = None
    phone_mobile: str | None = None
    whatsapp: str | None = None
    opening_hours: list[dict] | None = None
    insurances: list[str] | None = None
    tiers_payant: bool | None = None
    specialty_slugs: list[str] | None = None


class GrantAccessIn(BaseModel):
    """Credentials handed to a doctor at the end of the onboarding visit."""

    email: str
    password: str
