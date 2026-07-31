"""Articles: public reads, author writes, doctor validations, admin review.

Three audiences on one resource, so the guards matter more than usual. The
public sees only what a human approved. A doctor sees their own work whatever
its state, and may put their name to anything the platform wrote. An admin sees
the queue and is the only one who can write an article with no author.

Body of each handler: parse -> ONE controller call -> return.
"""

from fastapi import APIRouter, Depends, Query, Request
from sehaty.core.controllers.articles import (
    ArticleController,
    ArticleTraffic,
    ArticleView,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.articles import (
    ArticleEventIn,
    ArticleReviewIn,
    ArticleValidateIn,
    ArticleVoteIn,
    ArticleWriteIn,
    PlatformArticleIn,
)

router = APIRouter(prefix="/api/v1", tags=["articles"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_admin = require_roles(UserRole.ADMIN)


@router.get("/articles", response_model=list[ArticleView])
def list_articles(
    specialty: str | None = Query(default=None),
    locale: str | None = Query(default=None, pattern="^(ar|ary|fr)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ArticleView]:
    """Published answers, newest first. Public: no auth, no drafts."""
    return ArticleController.list_published(specialty_slug=specialty, locale=locale, limit=limit)


@router.get("/articles/{slug}", response_model=ArticleView)
def get_article(slug: str) -> ArticleView:
    """One published answer. A draft or a rejection is a 404, not a preview."""
    return ArticleController.get_published(slug)


def _fingerprint(request: Request) -> str:
    """What we know about a request, before it is hashed and forgotten.

    The client address plus the user agent. Neither is stored: the controller
    salts and hashes this into a per-article key, so what lands in the database
    identifies nobody and cannot be joined across articles.

    Behind the droplet's nginx the peer address is the proxy, so the forwarded
    header is preferred where present — otherwise every reader in the country
    would share one key and the first vote would lock out the rest.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    client = forwarded.split(",")[0].strip() or (request.client.host if request.client else "")
    return f"{client}|{request.headers.get('user-agent', '')}"


@router.post("/articles/{slug}/vote", response_model=ArticleView)
def vote_on_article(slug: str, body: ArticleVoteIn, request: Request) -> ArticleView:
    """Record whether this article helped the person reading it.

    Public and unauthenticated on purpose: requiring an account to say "this did
    not help me" would collect the opinion of the few people who already trust us
    and miss everyone we still have to convince.

    Returns the article with its new tally, so the page can show the result
    without a second request.
    """
    return ArticleController.vote(slug, fingerprint=_fingerprint(request), helpful=body.helpful)


@router.post("/articles/{slug}/events", status_code=204)
def record_article_event(slug: str, body: ArticleEventIn, request: Request) -> None:
    """Note a page view, or a reader following a doctor's name to their page.

    Public, unauthenticated and deliberately forgiving: an unknown slug or an
    unrecognised event type returns 204 rather than an error, because this is
    called from `navigator.sendBeacon` on a page a patient is reading and nothing
    here is worth failing that page for.

    The channel is taken from the beacon rather than the referrer header, so what
    is stored is "google" and never the query someone typed to get here.
    """
    ArticleController.record_event(
        slug, event=body.type, source=body.source, doctor_id=body.doctor_id
    )


@router.get("/admin/articles/traffic", response_model=list[ArticleTraffic])
def article_traffic(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(_require_admin),
) -> list[ArticleTraffic]:
    """What each article did, by channel, over the period.

    The evidence that should decide the next batch of topics. Until this table
    has data, topic choice runs on published disease prevalence — which measures
    who is ill rather than who is searching, and those are different people.
    """
    return ArticleController.traffic(days=days, limit=limit)


@router.get("/doctors/me/articles", response_model=list[ArticleView])
def my_articles(user: User = Depends(_require_doctor)) -> list[ArticleView]:
    """The author's own work, whatever state it is in."""
    return ArticleController.list_for_author(user.id)


@router.post("/doctors/me/articles", response_model=ArticleView, status_code=201)
def write_article(body: ArticleWriteIn, user: User = Depends(_require_doctor)) -> ArticleView:
    """Start a draft. Refused unless the doctor has claimed their page."""
    return ArticleController.write(
        user.id,
        title=body.title,
        body=body.body,
        summary=body.summary,
        locale=body.locale,
        specialty_slug=body.specialty_slug,
    )


@router.post("/doctors/me/articles/{article_id}/submit", response_model=ArticleView)
def submit_article(article_id: int, user: User = Depends(_require_doctor)) -> ArticleView:
    """Hand a draft to review. Submitting is asking, not publishing."""
    return ArticleController.submit(article_id, user.id)


@router.post("/doctors/me/articles/{article_id}/validate", response_model=ArticleView)
def validate_article(
    article_id: int,
    body: ArticleValidateIn,
    user: User = Depends(_require_doctor),
) -> ArticleView:
    """Put your name to an article the platform wrote.

    The doctor-facing half of the content strategy: five minutes of a physician's
    attention buys the article its standing, and buys the physician a byline on a
    page that links back to theirs. Refused unless they have claimed their page —
    an endorsement points at a doctor page, and an unclaimed one belongs to
    somebody who never agreed to any of this.
    """
    return ArticleController.validate(article_id, user.id, verdict=body.verdict, note=body.note)


@router.post("/admin/articles", response_model=ArticleView, status_code=201)
def write_platform_article(
    body: PlatformArticleIn,
    _admin: User = Depends(_require_admin),
) -> ArticleView:
    """Create a draft written from the medical literature, with no author.

    Admin-only because it is the one way to publish under the platform's name
    rather than a doctor's, and because these arrive in bulk from the generator.
    At least one source is required: an article that cites nothing gives the
    validating doctor nothing to check.
    """
    return ArticleController.write_from_sources(
        title=body.title,
        body=body.body,
        sources=[s.model_dump() for s in body.sources],
        summary=body.summary,
        locale=body.locale,
        specialty_slug=body.specialty_slug,
        images=[i.model_dump() for i in body.images],
    )


@router.get("/admin/articles/pending", response_model=list[ArticleView])
def pending_articles(
    limit: int = Query(default=100, ge=1, le=500),
    _admin: User = Depends(_require_admin),
) -> list[ArticleView]:
    """The review queue, oldest first."""
    return ArticleController.list_pending(limit)


@router.post("/admin/articles/{article_id}/review", response_model=ArticleView)
def review_article(
    article_id: int,
    body: ArticleReviewIn,
    _admin: User = Depends(_require_admin),
) -> ArticleView:
    """Publish it, or turn it down with a reason the author can act on."""
    return ArticleController.review(article_id, approve=body.approve, note=body.note)
