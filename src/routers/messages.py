"""Patient messaging router. Body of each handler: parse -> ONE controller call
-> return.

No SQLAlchemy here. A patient holds one 1:1 thread per doctor and drives it from
their own account — the caller's own user id is the ``patient_id``. Business
errors (the SehatyError taxonomy — ``SehatyForbiddenError`` -> 403,
``SehatyNotFoundError`` -> 404, ``SehatyValidationError`` -> 422) are mapped to
HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.messaging import MessagingController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.messaging import (
    MessageOut,
    PostMessageIn,
    StartThreadIn,
    ThreadDetailOut,
    ThreadOut,
    UnreadOut,
)

router = APIRouter(prefix="/api/v1/patient/messages", tags=["messages"])

_require_patient = require_roles(UserRole.PATIENT)


@router.get("", response_model=list[ThreadOut])
def list_threads(patient: User = Depends(_require_patient)) -> list[ThreadOut]:
    """The calling patient's inbox, newest-activity first, with per-thread unread."""
    rows = MessagingController.list_threads_for_patient(patient.id)
    return [ThreadOut.model_validate(row) for row in rows]


@router.post("", response_model=ThreadOut)
def start_thread(
    body: StartThreadIn,
    patient: User = Depends(_require_patient),
) -> ThreadOut:
    """Open (or return, idempotently) the thread with ``body.doctor_id``."""
    thread = MessagingController.start_or_get_thread(patient.id, body.doctor_id)
    return ThreadOut.model_validate(thread)


@router.get("/unread", response_model=UnreadOut)
def unread_total(patient: User = Depends(_require_patient)) -> UnreadOut:
    """Total unread messages across the calling patient's threads (nav badge)."""
    return UnreadOut(unread=MessagingController.unread_total_for_patient(patient.id))


@router.get("/{thread_id}", response_model=ThreadDetailOut)
def get_thread(
    thread_id: int,
    patient: User = Depends(_require_patient),
) -> ThreadDetailOut:
    """One thread + its messages (oldest->newest); marks the patient side read."""
    detail = MessagingController.get_thread(patient.id, thread_id)
    return ThreadDetailOut.model_validate(detail)


@router.post("/{thread_id}", response_model=MessageOut)
def post_message(
    thread_id: int,
    body: PostMessageIn,
    patient: User = Depends(_require_patient),
) -> MessageOut:
    """Append a message to the calling patient's thread (403/404 if not theirs)."""
    message = MessagingController.post_message(patient.id, thread_id, body.body)
    return MessageOut.model_validate(message)
