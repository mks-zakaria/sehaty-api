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


class SourceIn(BaseModel):
    """One work a platform-written article was drawn from."""

    work: str
    # Edition, chapter, page — whatever lets a doctor find the passage again.
    locator: str | None = None


class ImageIn(BaseModel):
    """An illustration brief, and the sourced image once it exists."""

    brief: str | None = None
    alt: str | None = None
    url: str | None = None
    credit: str | None = None
    credit_url: str | None = None


class PlatformArticleIn(BaseModel):
    """An article the platform wrote from the literature.

    No author field: these carry no single professional opinion, and attributing
    one to a doctor who did not write it is the failure this whole flow is built
    to avoid. Attribution comes later, from the doctors who validate it.
    """

    title: str
    body: str
    sources: list[SourceIn]
    summary: str | None = None
    locale: str = "ar"
    specialty_slug: str | None = None
    images: list[ImageIn] = []


class ArticleValidateIn(BaseModel):
    """A doctor putting their name to an article.

    `note` is required for RECTIFIED and ENRICHED — enforced in the controller,
    because "say what you changed" is a rule about the product and not about the
    shape of the request.
    """

    verdict: str = "VALIDATED"
    note: str | None = None


class ArticleVoteIn(BaseModel):
    """A reader's answer to "did this article help you?"."""

    helpful: bool


class ArticleEventIn(BaseModel):
    """A fire-and-forget beacon from a published article."""

    type: str
    source: str | None = None
    # Set on a DOCTOR_CLICK: which validating doctor was followed.
    doctor_id: int | None = None


class ArticleEditIn(BaseModel):
    """A partial edit from the admin console.

    Every field is optional and omitting one means "leave it alone", which is
    what lets the editor save a title fix without resending an entire article
    and silently overwriting a field it never showed.

    Sending `summary: ""` clears the summary; omitting `summary` keeps it. The
    two are different requests and the console has to mean the one it sends.

    Changing `body` costs the article its doctors' validations — the controller
    drops them, because a signature on words that have since changed is worse
    than no signature at all.
    """

    title: str | None = None
    summary: str | None = None
    body: str | None = None
    locale: str | None = None
    specialty_slug: str | None = None
    topic_key: str | None = None
    images: list[ImageIn] | None = None
    sources: list[SourceIn] | None = None
