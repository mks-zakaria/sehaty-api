"""Assistant-management router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. A doctor onboards a secretary/assistant (an ASSISTANT-role
``User`` with a login) who then acts within that doctor's workspace. The DOCTOR
routes are doctor-scoped — the caller's own user id is the ``doctor_id``; the
ASSISTANT route is scoped to the caller's own assistant id. Business errors
raised by the controller (the SehatyError taxonomy — ``SehatyConflictError`` ->
409, ``SehatyValidationError`` -> 422, ``SehatyNotFoundError`` -> 404) are
mapped to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, Response, status
from sehaty.core.controllers.assistants import AssistantController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.assistant import (
    AssistantCreateIn,
    AssistantLinkIn,
    AssistantOut,
    DoctorRefOut,
)

router = APIRouter(prefix="/api/v1", tags=["assistants"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_assistant = require_roles(UserRole.ASSISTANT)


@router.post(
    "/doctor/assistants",
    response_model=AssistantOut,
    status_code=status.HTTP_201_CREATED,
)
def create_assistant(
    body: AssistantCreateIn,
    doctor: User = Depends(_require_doctor),
) -> AssistantOut:
    """Onboard a new ASSISTANT account and link it to the calling doctor."""
    row = AssistantController.create_assistant_account(
        doctor_id=doctor.id,
        email=body.email,
        phone=body.phone,
        full_name=body.full_name,
        password=body.password,
    )
    return AssistantOut.model_validate(row)


@router.post("/doctor/assistants/link", status_code=status.HTTP_204_NO_CONTENT)
def link_assistant(
    body: AssistantLinkIn,
    doctor: User = Depends(_require_doctor),
) -> Response:
    """Link an existing ASSISTANT user to the calling doctor (idempotent)."""
    AssistantController.link_existing(doctor.id, body.assistant_user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/doctor/assistants", response_model=list[AssistantOut])
def list_assistants(
    doctor: User = Depends(_require_doctor),
) -> list[AssistantOut]:
    """List the calling doctor's active assistants."""
    rows = AssistantController.list_assistants(doctor.id)
    return [AssistantOut.model_validate(r) for r in rows]


@router.delete("/doctor/assistants/{assistant_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_assistant(
    assistant_id: int,
    doctor: User = Depends(_require_doctor),
) -> Response:
    """Deactivate a doctor<->assistant link (404 if no active membership)."""
    AssistantController.remove_assistant(doctor.id, assistant_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/assistant/doctors", response_model=list[DoctorRefOut])
def list_doctors_for_assistant(
    assistant: User = Depends(_require_assistant),
) -> list[DoctorRefOut]:
    """List the doctors the calling assistant actively works for."""
    refs = AssistantController.list_doctors_for_assistant(assistant.id)
    return [DoctorRefOut.model_validate(r) for r in refs]
