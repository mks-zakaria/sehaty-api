"""Request/response DTOs for the assistant-management surface — boundary only.

No business logic, no DB access. The ``*Out`` models translate the core
``AssistantController`` frozen dataclass projections (``AssistantRow``,
``DoctorRef``) into the JSON contract clients consume; the ``*In`` models parse
the request bodies. A doctor onboards a secretary/assistant (an ASSISTANT-role
``User`` with a login) who then acts within that doctor's workspace; the
membership and acting-doctor resolution live in ``AssistantController``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AssistantCreateIn(BaseModel):
    """Onboard a new assistant account (the ``POST /doctor/assistants`` body)."""

    email: str
    phone: str | None = None
    full_name: str | None = None
    password: str


class AssistantLinkIn(BaseModel):
    """Link an existing ASSISTANT user (the ``POST /doctor/assistants/link`` body)."""

    assistant_user_id: int


class AssistantOut(BaseModel):
    """One assistant account (the core ``AssistantRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    phone: str | None = None
    full_name: str | None = None
    is_active: bool
    created_at: datetime


class DoctorRefOut(BaseModel):
    """A doctor an assistant works for (the core ``DoctorRef``)."""

    model_config = ConfigDict(from_attributes=True)

    doctor_id: int
    full_name: str | None = None
