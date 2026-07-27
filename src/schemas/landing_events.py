"""Request/response DTOs for the landing-analytics surface.

No PII by design: a beacon carries the doctor's public slug, what happened, and
a coarse traffic bucket. It never carries who the visitor is, their IP, their
user agent or a full referrer — a referrer can hold a search query, and a query
typed before landing on a specialist's page is health data about a person we
have no relationship with.
"""

from pydantic import BaseModel, Field


class LandingEventIn(BaseModel):
    """One public-page interaction, posted by the landing site."""

    slug: str = Field(description="Public doctor slug the event belongs to.")
    type: str = Field(
        description=(
            "PAGE_VIEW | QR_SCAN | CALL_CLICK | WHATSAPP_CLICK | DIRECTIONS_CLICK | BOOK_CLICK"
        )
    )
    source: str | None = Field(
        default=None,
        description="Coarse traffic bucket: qr, google, direct, whatsapp, other.",
    )


class LandingEventOut(BaseModel):
    """Whether the event was attributed to a published doctor and stored."""

    recorded: bool
