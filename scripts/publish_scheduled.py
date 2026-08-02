#!/usr/bin/env python
"""Publish the articles whose scheduled time has passed.

Run by `.github/workflows/scheduler.yml` every couple of hours, inside the api
container on the droplet — the same path the other maintenance tasks take, so
no production admin token is ever minted to publish an article.

The work is `ArticleController.publish_due`, which is where the rules live: a
draft with no date is never touched, a rejection is never resurrected, and the
date is cleared on publication so a replay cannot redate the archive. This
script is the thin shell around it, and its own job is to report clearly enough
that a run nobody watched can still be read afterwards.

    python scripts/publish_scheduled.py --dry-run   # what would go live
    python scripts/publish_scheduled.py             # publish it
    python scripts/publish_scheduled.py --limit 3   # take a smaller bite
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# How many one run will publish. A backlog drains over several runs rather than
# landing at once: twelve articles appearing in the same minute reads as a dump
# to a crawler, and gives a returning reader nothing new to come back for.
DEFAULT_LIMIT = 4


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what is due without publishing it.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Most to publish in one run (default {DEFAULT_LIMIT}).",
    )
    args = parser.parse_args()

    from sehaty.core.controllers.articles import ArticleController

    now = datetime.now(UTC)

    if args.dry_run:
        queued = ArticleController.list_scheduled(limit=200)
        due = [a for a in queued if a.scheduled_for and a.scheduled_for <= now]
        for article in due[: args.limit]:
            print(f"  → {article.locale}  {article.title[:60]}", file=sys.stderr)
        # The rest of the queue is printed too: the useful question when reading
        # a scheduler's output is usually "what is coming", not "what just ran".
        for article in queued:
            if article.scheduled_for and article.scheduled_for > now:
                when = article.scheduled_for.strftime("%Y-%m-%d %H:%M")
                print(f"    {when}  {article.locale}  {article.title[:50]}", file=sys.stderr)
        print(
            f"\n{min(len(due), args.limit)} would publish, "
            f"{max(len(due) - args.limit, 0)} would wait for the next run, "
            f"{len(queued) - len(due)} still scheduled",
            file=sys.stderr,
        )
        return 0

    published = ArticleController.publish_due(now=now, limit=args.limit)
    for article in published:
        print(f"  + {article.locale}  {article.slug[:60]}", file=sys.stderr)

    remaining = [a for a in ArticleController.list_scheduled(limit=200) if a.scheduled_for]
    still_due = sum(1 for a in remaining if a.scheduled_for and a.scheduled_for <= now)
    print(
        f"\n{len(published)} published, {still_due} still due, "
        f"{len(remaining) - still_due} scheduled later",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
