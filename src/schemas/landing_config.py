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
    accent: str | None = Field(default=None, description="Hex colour, e.g. #2b73b3.")
    section_order: list[str] | None = None
    services: list[ServiceIn] | None = None
    equipment: list[str] | None = None
    faq: list[FaqIn] | None = None
    tagline: str | None = None


class PersonalizedIn(BaseModel):
    """Turn the paid personalisation on or off — recorded when the pack sells."""

    enabled: bool
