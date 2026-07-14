"""In-app notification router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. A ``Notification`` is an unread in-app message addressed to
a single recipient; every route below is scoped to the calling authenticated
user (``get_current_user``), so the feed a caller reads and the notifications
they mark read are always their own — marking another user's notification read
is a ``SehatyForbiddenError`` in core. Business errors (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.notifications import NotificationController
from sehaty.db import User

from deps import get_current_user
from schemas.notification import NotificationOut

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    user: User = Depends(get_current_user),
) -> list[NotificationOut]:
    """The calling user's notifications, newest first (the bell feed).

    ``unread_only`` filters to unread rows; ``limit`` caps the page size.
    """
    notifications = NotificationController.list_for(user.id, unread_only, limit)
    return [NotificationOut.model_validate(n) for n in notifications]


@router.get("/unread-count")
def unread_count(
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    """The calling user's unread notification count (the bell badge)."""
    return {"unread": NotificationController.unread_count(user.id)}


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
) -> NotificationOut:
    """Mark one of the caller's own notifications read; return the updated row.

    Idempotent (already-read is a no-op). 404 on a missing id; 403 on a
    notification owned by another user.
    """
    notification = NotificationController.mark_read(user.id, notification_id)
    return NotificationOut.model_validate(notification)


@router.post("/read-all")
def mark_all_read(
    user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Mark every unread notification for the caller read; return the count."""
    return {"marked": NotificationController.mark_all_read(user.id)}
