"""Reviews router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. A review is only possible off the back of a *completed*
appointment the author was a party to (the booking gate, enforced in core), and
lands ``PENDING`` until an admin moderates it. Business errors (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.reviews import ReviewController, ReviewRow
from sehaty.db import User

from deps import get_current_user
from schemas.reviews import ReviewIn, ReviewReplyIn

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


@router.post("", response_model=ReviewRow, status_code=status.HTTP_201_CREATED)
def create_review(
    body: ReviewIn,
    user: User = Depends(get_current_user),
) -> ReviewRow:
    """Create a ``PENDING`` review behind the booking gate (409 if not completed)."""
    return ReviewController.create(
        user.id, body.appointment_id, body.direction, body.stars, body.comment
    )


@router.post("/{review_id}/reply", response_model=ReviewRow)
def reply_review(
    review_id: int,
    body: ReviewReplyIn,
    user: User = Depends(get_current_user),
) -> ReviewRow:
    """Post the rated party's one right-of-reply (403 for anyone else)."""
    return ReviewController.reply(user.id, review_id, body.text)


@router.post("/{review_id}/flag", response_model=ReviewRow)
def flag_review(
    review_id: int,
    user: User = Depends(get_current_user),
) -> ReviewRow:
    """Flag a review for moderation (any authenticated user)."""
    return ReviewController.flag(user.id, review_id)
