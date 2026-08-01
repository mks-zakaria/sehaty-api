#!/usr/bin/env python3
"""Publish a batch of written articles through the admin API.

The articles themselves are tracked (`scripts/data/articles/*.jsonl`), unlike the
textbook corpora they were written from: this is our own writing, and it is the
asset. Losing it to a laptop would cost more than losing the code.

Idempotent by title. Re-running skips anything already on the platform, so this
is safe to point at production twice — which is what will happen the first time
a batch is half-published and something times out.

Nothing here writes to the database directly. It goes through the same admin
endpoints an operator uses, so the review and validation rules apply to a bulk
publish exactly as they do to a single article.

Usage:

    python scripts/publish_articles.py \\
        --file scripts/data/articles/batch-2026-07.jsonl \\
        --api https://api.example.ma --token "$ADMIN_TOKEN"

    # See what would happen, touching nothing:
    python scripts/publish_articles.py --file ... --api ... --token ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


def call(api: str, path: str, token: str, payload: dict | None = None) -> dict | None:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"{api.rstrip('/')}{path}",
        data=data,
        method="POST" if data else "GET",
        headers={"Authorization": f"Bearer {token}", "content-type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response) if response.status != 204 else None


def _publish_direct(drafts: list[dict], *, publish: bool, dry_run: bool) -> int:
    """Write straight through the controllers, no HTTP and no token.

    The same path the other droplet maintenance tasks take. It exists so that
    publishing a batch never requires a production admin token to be minted,
    pasted into a terminal or carried through a chat window — the operation runs
    where the credentials already are.

    The rules still apply: this calls the same controller the API calls, so the
    source requirement and the review step are enforced exactly as they are for
    a single article created from the console.
    """
    # Imported here so the HTTP path keeps working outside the container, where
    # sehaty.core is not necessarily installed.
    from sehaty.core.controllers.articles import ArticleController
    from sehaty.core.db.session import get_session
    from sehaty.db import Article, ArticleStatus
    from sqlalchemy import select

    # Titles already imported, at *any* status. Matching only against published
    # ones would make the drafts run non-idempotent: nothing it wrote would be
    # visible to the next run, so a second one would import the batch again.
    with get_session() as session:
        existing = {
            title: (article_id, status)
            for article_id, title, status in session.execute(
                select(Article.id, Article.title, Article.status)
            ).all()
        }
    created = promoted = skipped = 0
    for draft in drafts:
        if draft["title"] in existing:
            article_id, status = existing[draft["title"]]
            # The batch was drafted by an earlier run and is being published
            # now. Skipping here would make the two-step flow — draft, read,
            # then publish — a dead end: the second run would report everything
            # "already present" and nothing would ever go live.
            if publish and status != ArticleStatus.PUBLISHED:
                if not dry_run:
                    ArticleController.review(article_id, approve=True)
                promoted += 1
                print(f"  ^ {draft['locale']}  {draft['title'][:56]}", file=sys.stderr)
            else:
                skipped += 1
            continue
        if dry_run:
            created += 1
            print(f"  + {draft['locale']}  {draft['title'][:56]} (dry run)", file=sys.stderr)
            continue
        article = ArticleController.write_from_sources(
            title=draft["title"],
            body=draft["body"],
            sources=draft["sources"],
            summary=draft.get("summary"),
            locale=draft.get("locale", "ar"),
            specialty_slug=draft.get("specialty_slug"),
            images=draft.get("images"),
        )
        if publish:
            ArticleController.review(article.id, approve=True)
        created += 1
        print(f"  + {article.locale}  {article.slug[:56]}", file=sys.stderr)

    state = "published" if publish else "drafted"
    if dry_run:
        state = f"would be {state}"
    summary = f"\n{created} {state}"
    if promoted:
        summary += f", {promoted} existing draft{'s' if promoted > 1 else ''} published"
    summary += f", {skipped} already present"
    print(summary, file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--api", default=None, help="API base URL. Omit with --direct.")
    parser.add_argument("--token", default=None, help="Admin bearer token. Omit with --direct.")
    parser.add_argument(
        "--direct",
        action="store_true",
        help=(
            "Write through the controllers instead of over HTTP. For running "
            "inside the api container on the droplet, where there is no token to "
            "hold and no secret to hand around."
        ),
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also approve them. Without this they land as drafts for a human to read.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    drafts = [json.loads(line) for line in lines if line.strip()]

    if args.direct:
        return _publish_direct(drafts, publish=args.publish, dry_run=args.dry_run)
    if not (args.api and args.token):
        raise SystemExit("--api and --token are required unless --direct is given")

    existing = {a["title"] for a in (call(args.api, "/api/v1/articles", args.token) or [])}

    created = skipped = 0
    for draft in drafts:
        if draft["title"] in existing:
            skipped += 1
            print(f"  = {draft['locale']}  {draft['title'][:56]}", file=sys.stderr)
            continue
        if args.dry_run:
            created += 1
            print(f"  + {draft['locale']}  {draft['title'][:56]} (dry run)", file=sys.stderr)
            continue
        try:
            article = call(args.api, "/api/v1/admin/articles", args.token, draft)
        except urllib.error.HTTPError as error:
            print(f"  ! {draft['title'][:48]}: {error.read().decode()[:140]}", file=sys.stderr)
            continue
        # Publishing is opt-in. A batch that goes live unreviewed is exactly the
        # failure the review step exists to prevent, however good the drafts are.
        if args.publish:
            call(
                args.api,
                f"/api/v1/admin/articles/{article['id']}/review",
                args.token,
                {"approve": True},
            )
        created += 1
        print(f"  + {article['locale']}  {article['slug'][:56]}", file=sys.stderr)

    state = "published" if args.publish else "drafted"
    print(f"\n{created} {state}, {skipped} already present", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
