"""Messaging DTOs — boundary translation over the core projections.

Maps ``MessagingController``'s frozen dataclasses (``MessageView``,
``ThreadView``, ``ThreadDetail``) onto the JSON contract the patient and clinic
chat surfaces consume, plus the two request bodies. ``from_attributes`` reads the
dataclasses straight through; no business logic, no DB access.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    sender_id: int
    body: str
    created_at: datetime
    mine: bool


class ThreadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    patient_id: int
    doctor_id: int
    doctor_name: str | None = None
    patient_name: str | None = None
    last_message_at: datetime | None = None
    unread: int
    last_message_preview: str | None = None


class ThreadDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    thread: ThreadOut
    messages: list[MessageOut]


class UnreadOut(BaseModel):
    unread: int


class StartThreadIn(BaseModel):
    doctor_id: int


class PostMessageIn(BaseModel):
    body: str
