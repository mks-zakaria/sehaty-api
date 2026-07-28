"""Request DTOs for the articles surface — boundary translation only."""

from pydantic import BaseModel


class ArticleWriteIn(BaseModel):
    """A doctor's answer to a patient's question."""

    title: str
    body: str
    summary: str | None = None
    locale: str = "ar"
    specialty_slug: str | None = None


class ArticleReviewIn(BaseModel):
    """A reviewer's verdict. A rejection must carry a reason."""

    approve: bool
    note: str | None = None
