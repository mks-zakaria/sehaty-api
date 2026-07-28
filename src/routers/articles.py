"""Doctor-written answers: public reads, author writes, admin review.

Three audiences on one resource, so the guards matter more than usual. The
public sees only what a human approved. A doctor sees their own work whatever
its state. An admin sees the queue.

Body of each handler: parse -> ONE controller call -> return.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.articles import ArticleController, ArticleView
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.articles import ArticleReviewIn, ArticleWriteIn

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
