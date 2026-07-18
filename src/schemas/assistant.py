"""Request DTOs for the assistant-management surface — boundary only.

No business logic, no DB access. The ``*In`` models parse the request bodies;
responses are served directly from the core ``AssistantController`` projections
(``AssistantRow``, ``DoctorRef``), which are pydantic models used as FastAPI
``response_model`` without a parallel ``*Out`` mirror. A doctor onboards a
secretary/assistant (an ASSISTANT-role ``User`` with a login) who then acts
within that doctor's workspace; the membership and acting-doctor resolution live
in ``AssistantController``.
"""

from pydantic import BaseModel


class AssistantCreateIn(BaseModel):
    """Onboard a new assistant account (the ``POST /doctor/assistants`` body)."""

    email: str
    phone: str | None = None
    full_name: str | None = None
    password: str


class AssistantLinkIn(BaseModel):
    """Link an existing ASSISTANT user (the ``POST /doctor/assistants/link`` body)."""

    assistant_user_id: int
