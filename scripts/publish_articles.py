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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--api", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument(
        "--publish",
        action="store_true",
        help="Also approve them. Without this they land as drafts for a human to read.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    lines = args.file.read_text(encoding="utf-8").splitlines()
    drafts = [json.loads(line) for line in lines if line.strip()]
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
