"""Request/response DTOs for the reviews surface — boundary translation.

No business logic, no DB access. ``*In`` models parse the request body; the
``*Out`` model translates a ``sehaty.db.Review`` ORM row into the JSON contract
clients consume. The booking gate, moderation state machine and reputation
recompute all live in ``ReviewController``.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sehaty.db import ReviewDirection, ReviewStatus


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


class ReviewOut(BaseModel):
    """A review as seen on the wire (public list, moderation queue, or mutations)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    author_id: int
    target_id: int
    appointment_id: int
    direction: ReviewDirection
    stars: int
    comment: str | None = None
    status: ReviewStatus
    reply: str | None = None
    reply_at: datetime | None = None
    created_at: datetime
