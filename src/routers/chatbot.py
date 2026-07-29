"""The chatbot: patient triage, and translation help for the console.

Named `chatbot`, not `assistant` — an "assistant" in this codebase is the person
at a cabinet's front desk, and reusing the word is how the wrong module gets
imported at three in the morning.

Triage is public — a patient describing a problem has no account yet, and
requiring one to ask "which doctor do I need" would defeat the purpose.
Translation is admin-only: it drafts text that ends up on a doctor's page.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.assistant import (
    AssistantController,
    TranslationDraft,
    Triage,
)
from sehaty.core.services.llm import LLMUnavailable
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.chatbot import TranslateIn, TriageIn

router = APIRouter(prefix="/api/v1/chatbot", tags=["chatbot"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/status")
def assistant_status() -> dict[str, bool]:
    """Whether the assistant can answer at all.

    Checked before a screen offers a chat box, so nobody is invited to type a
    question into something with no key behind it.
    """
    return {"available": AssistantController.available()}


@router.post("/triage", response_model=Triage)
def triage(body: TriageIn) -> Triage:
    """Route a described problem to a specialty.

    Public on purpose. Always answers: without a model it falls back to a
    generalist, which is a safe answer, and urgent wording is matched before any
    model is consulted and returned with emergency numbers.
    """
    return AssistantController.triage(body.complaint, locale=body.locale)


@router.post("/translate", response_model=TranslationDraft)
def translate(body: TranslateIn, _admin: User = Depends(_require_admin)) -> TranslationDraft:
    """Draft a presentation in the other two languages, for review.

    A draft, never a save — the operator reads it before it reaches a page.
    """
    try:
        return AssistantController.translate(body.text, source_locale=body.locale)
    except LLMUnavailable as exc:
        from fastapi import HTTPException

        # 503 rather than 500: nothing is broken, the assistant is simply not
        # configured yet, and the console should say so rather than look faulty.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
