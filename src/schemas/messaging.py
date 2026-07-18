"""Messaging inbound DTOs + the unread badge response.

The response projections (``MessageView``, ``ThreadView``, ``ThreadDetail``) live
on ``MessagingController`` and are consumed by the routers directly as pydantic
``response_model``; this module holds only the request bodies and the scalar
``UnreadOut`` badge (built from an ``int``, so it has no core projection).
"""

from pydantic import BaseModel


class UnreadOut(BaseModel):
    unread: int


class StartThreadIn(BaseModel):
    doctor_id: int


class PostMessageIn(BaseModel):
    body: str
