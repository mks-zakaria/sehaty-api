"""Claim / delist a published doctor page.

Both endpoints are public and unauthenticated by design. A doctor who discovers
a page about themselves has no account here yet — requiring one before they can
object would make the objection route useless to exactly the people who need it.

``POST /removal`` takes the page down immediately. Verification of who asked
happens afterwards; leaving a contested listing up during review gets the order
backwards.
"""

from fastapi import APIRouter, status
from sehaty.core.controllers.claims import ClaimController, ClaimRequestResult

from schemas.claims import ClaimIn, RemovalIn

router = APIRouter(prefix="/api/v1/claims", tags=["claims"])


@router.post("/removal", response_model=ClaimRequestResult, status_code=status.HTTP_202_ACCEPTED)
def request_removal(body: RemovalIn) -> ClaimRequestResult:
    """Delist a doctor's public page at their request, effective immediately.

    Idempotent — a doctor chasing a removal must never be told their second
    request failed. An unknown slug is a 404 via the SehatyError handler.
    """
    return ClaimController.request_removal(body.slug, reason=body.reason)


@router.post("", response_model=ClaimRequestResult, status_code=status.HTTP_202_ACCEPTED)
def claim_page(body: ClaimIn) -> ClaimRequestResult:
    """Record that a doctor is claiming an unclaimed page.

    Marks it CLAIMED, never VERIFIED: confirming identity against the licence is
    a separate, human step, and a trust badge must not follow from a self-report.
    """
    return ClaimController.mark_claimed(body.slug)
