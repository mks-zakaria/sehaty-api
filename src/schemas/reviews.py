"""Request DTOs for the reviews surface — boundary translation.

No business logic, no DB access. ``*In`` models parse the request body. The
outbound contract is served directly by ``ReviewController``'s ``ReviewRow``
projection (no ``*Out`` mirror). The booking gate, moderation state machine and
reputation recompute all live in ``ReviewController``.
"""

from typing import Literal

from pydantic import BaseModel, Field
from sehaty.db import ReviewDirection


class ReviewIn(BaseModel):
    """A new review (the ``POST /reviews`` body).

    Maps one-to-one onto ``ReviewController.create``: the author must be a party
    to a ``COMPLETED`` appointment matching ``direction`` (validated in core).
    """

    appointment_id: int
    direction: ReviewDirection
    stars: int = Field(ge=1, le=5)
    comment: str | None = None


class ReviewReplyIn(BaseModel):
    """The rated party's one right-of-reply (the ``POST /reviews/{id}/reply`` body)."""

    text: str


class ReviewModerateIn(BaseModel):
    """An admin moderation decision (the ``POST /admin/reviews/{id}/moderate`` body)."""

    action: Literal["PUBLISH", "REMOVE"]
