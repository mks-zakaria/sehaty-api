"""Request DTOs for the public claim / delist surface."""

from pydantic import BaseModel, Field


class RemovalIn(BaseModel):
    """A doctor asking for their published page to be taken down."""

    slug: str = Field(description="Public doctor slug to delist.")
    reason: str | None = Field(
        default=None,
        description="Optional free-text reason, kept for audit (truncated).",
    )


class ClaimIn(BaseModel):
    """A doctor claiming ownership of an unclaimed page."""

    slug: str = Field(description="Public doctor slug being claimed.")
