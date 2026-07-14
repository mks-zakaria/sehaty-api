"""Response DTO for the in-app notification (bell feed) surface.

No business logic, no DB access. ``NotificationOut`` translates the
``sehaty.db`` ``Notification`` ORM row into the JSON contract clients consume.
The bell feed, unread badge and mark-read semantics all live in
``NotificationController``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    """A single in-app notification as seen on the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    message: str
    entity: str | None = None
    entity_id: int | None = None
    is_read: bool
    created_at: datetime
