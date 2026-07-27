"""Confirmations, the secretary day view, and the waitlist.

The doctor/secretary side is authenticated; the WhatsApp webhook is public and
verified by Meta's challenge + a shared verify token.

Body of each handler: parse -> ONE controller call -> return.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sehaty.core.controllers.confirmations import (
    ConfirmationController,
    DaySummary,
)
from sehaty.core.controllers.waitlist import (
    OfferResult,
    WaitlistController,
    WaitlistRow,
)
from sehaty.core.services.whatsapp import (
    interpret_reply,
    load_config,
    parse_inbound,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.confirmations import (
    ConfirmationReplyIn,
    ConfirmationSentIn,
    WaitlistJoinIn,
)

router = APIRouter(prefix="/api/v1", tags=["confirmations"])

# The secretary works the day view on the doctor's behalf, so both roles reach it.
_require_practice = require_roles(UserRole.DOCTOR, UserRole.ASSISTANT)
_require_patient = require_roles(UserRole.PATIENT)


@router.get("/practice/day", response_model=DaySummary)
def day_view(
    day: date = Query(description="Calendar day to show."),
    doctor_id: int | None = Query(
        default=None, description="Doctor to view; defaults to the caller."
    ),
    user: User = Depends(_require_practice),
) -> DaySummary:
    """The day's appointments, scored for no-show risk and ready to chase."""
    return ConfirmationController.day_view(doctor_id or user.id, day)


@router.post(
    "/appointments/{appointment_id}/confirmation/sent",
    status_code=status.HTTP_204_NO_CONTENT,
)
def mark_confirmation_sent(
    appointment_id: int,
    body: ConfirmationSentIn,
    _user: User = Depends(_require_practice),
) -> Response:
    """Record that the secretary sent the confirmation ask (v1 manual flow)."""
    ConfirmationController.mark_sent(appointment_id, channel=body.channel, template=body.template)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/appointments/{appointment_id}/confirmation/reply")
def record_confirmation_reply(
    appointment_id: int,
    body: ConfirmationReplyIn,
    _user: User = Depends(_require_practice),
) -> dict[str, str]:
    """Record the patient's answer, however it was obtained (often by phone)."""
    return {
        "confirmation_status": ConfirmationController.record_reply(
            appointment_id, confirmed=body.confirmed
        )
    }


@router.post("/appointments/{appointment_id}/release", response_model=OfferResult)
def release_slot(
    appointment_id: int,
    _user: User = Depends(_require_practice),
) -> OfferResult:
    """Free a slot and offer it to the next patient on the waitlist.

    One call rather than two: a slot freed but never offered is the failure the
    whole feature exists to prevent.
    """
    return WaitlistController.release_slot(appointment_id)


@router.get("/practice/waitlist", response_model=list[WaitlistRow])
def practice_waitlist(
    doctor_id: int | None = Query(default=None),
    user: User = Depends(_require_practice),
) -> list[WaitlistRow]:
    """The doctor's live waitlist, oldest first."""
    return WaitlistController.queue(doctor_id or user.id)


@router.post("/waitlist", status_code=status.HTTP_201_CREATED)
def join_waitlist(body: WaitlistJoinIn, user: User = Depends(_require_patient)) -> dict[str, int]:
    """Ask to be told when a slot frees up with this doctor."""
    return {
        "entry_id": WaitlistController.join(
            body.doctor_id,
            user.id,
            earliest_at=body.earliest_at,
            latest_at=body.latest_at,
            note=body.note,
        )
    }


@router.delete("/waitlist/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def leave_waitlist(entry_id: int, user: User = Depends(_require_patient)) -> Response:
    """Leave a waitlist (the caller's own entry only)."""
    WaitlistController.leave(entry_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/waitlist/{entry_id}/accept")
def accept_offer(entry_id: int, user: User = Depends(_require_patient)) -> dict[str, int]:
    """Take an offered slot."""
    return {"appointment_id": WaitlistController.accept_offer(entry_id, user.id)}


@router.post("/waitlist/{entry_id}/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_offer(entry_id: int, user: User = Depends(_require_patient)) -> Response:
    """Turn down an offered slot and stay on the list."""
    WaitlistController.decline_offer(entry_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/webhooks/whatsapp")
def verify_whatsapp_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> Response:
    """Meta's subscription handshake: echo the challenge if the token matches."""
    config = load_config()
    if mode == "subscribe" and config.verify_token and token == config.verify_token:
        return Response(content=challenge or "", media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("/webhooks/whatsapp", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(request: Request) -> dict[str, int]:
    """Ingest patient replies and update the matching appointments.

    Always answers 200, even for payloads it cannot use: Meta retries non-2xx
    responses aggressively and disables endpoints that keep failing, so a
    surprising message shape must not take the integration down.
    """
    try:
        payload = await request.json()
    except ValueError:
        return {"processed": 0}

    processed = 0
    for message in parse_inbound(payload):
        verdict = interpret_reply(message.get("text"), message.get("button"))
        if verdict is None:
            # Unclear replies are left for a human rather than guessed at.
            continue
        appointment_id = ConfirmationController.appointment_awaiting_reply(message.get("from"))
        if appointment_id is None:
            continue
        ConfirmationController.record_reply(appointment_id, confirmed=verdict)
        processed += 1

    return {"processed": processed}
