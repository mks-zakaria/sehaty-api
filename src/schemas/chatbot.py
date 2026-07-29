"""Request DTOs for the chatbot — boundary translation only.

Named `chatbot` rather than `assistant` because `assistant` already means the
medical assistant who works a cabinet's front desk, and two different things
called the same word in one codebase is how the wrong one gets imported.
"""

from pydantic import BaseModel


class TriageIn(BaseModel):
    """A patient's own words, in their own language."""

    complaint: str
    locale: str = "fr"


class TranslateIn(BaseModel):
    """A presentation written in one language, to be drafted into the others."""

    text: str
    locale: str = "fr"
