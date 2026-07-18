"""Clinic messaging router. Body of each handler: parse -> ONE controller call
-> return.

No SQLAlchemy here. The clinic side of a thread is reachable by BOTH the doctor
and any ASSISTANT who actively works for that doctor. Thread listing/unread are
scoped to the *effective* doctor, resolved via ``get_acting_doctor_id`` (the same
dependency the doctor-appointment grid uses — it authorizes the assistant<->doctor
link and rejects a patient/unlinked caller with 403). The per-thread reads and
sends carry the caller's OWN user id as the participant/sender, so an assistant's
message records their id; core authorizes the caller against the thread via its
own clinic-side link check. Business errors (the SehatyError taxonomy) are mapped
to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.messaging import (
    MessageView,
    MessagingController,
    ThreadDetail,
    ThreadView,
)
from sehaty.db import User, UserRole

from deps import get_acting_doctor_id, require_roles
from schemas.messaging import (
    PostMessageIn,
    UnreadOut,
)

router = APIRouter(prefix="/api/v1/doctor/messages", tags=["messages"])

_require_clinic = require_roles(UserRole.DOCTOR, UserRole.ASSISTANT)


@router.get("", response_model=list[ThreadView])
def list_threads(
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> list[ThreadView]:
    """The (acting) doctor's clinic inbox, newest-activity first, with unread."""
    return MessagingController.list_threads_for_doctor(acting_doctor_id)


@router.get("/unread", response_model=UnreadOut)
def unread_total(
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> UnreadOut:
    """Total unread across the (acting) doctor's threads (nav badge)."""
    return UnreadOut(unread=MessagingController.unread_total_for_doctor(acting_doctor_id))


@router.get("/{thread_id}", response_model=ThreadDetail)
def get_thread(
    thread_id: int,
    caller: User = Depends(_require_clinic),
) -> ThreadDetail:
    """One thread + its messages (oldest->newest); marks the clinic side read.

    The caller's own id is the viewer, so ``mine`` reflects the actual author and
    core authorizes a doctor or the doctor's active assistant (403 otherwise).
    """
    return MessagingController.get_thread(caller.id, thread_id)


@router.post("/{thread_id}", response_model=MessageView)
def post_message(
    thread_id: int,
    body: PostMessageIn,
    caller: User = Depends(_require_clinic),
) -> MessageView:
    """Append a clinic message; the caller's own id is the sender (403/404 on abuse)."""
    return MessagingController.post_message(caller.id, thread_id, body.body)
