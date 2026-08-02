#!/usr/bin/env python
"""Re-time the publishing calendar across every batch file.

The dates live in the batch files, so changing the cadence means rewriting them
— and re-running each batch re-applies its dates, which is how the change
reaches the queue. This edits the files; `publish_articles.py` pushes them.

The unit scheduled here is the *topic*, not the article. An answer written in
French and in Arabic is one thing said twice, and the two go live together:
publishing them apart leaves the language switch on the live version pointing
at an article nobody can read yet, which is the one moment a reader is most
likely to want it.

So a run of three articles a day is three *slots* a day filled by whole pairs —
some days take two topics, some one, and the average lands where it was asked
to. Nothing is split across a midnight to make an average come out exactly.

    python scripts/retime_calendar.py --per-day 3 --start 2026-08-04 --dry-run
    python scripts/retime_calendar.py --per-day 3 --start 2026-08-04
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

DATA = Path(__file__).parent / "data" / "articles"

# Publishing hour, UTC. Morocco is UTC+1, so this is a nine o'clock morning —
# a weekday hour when people read, not an overnight dump.
HOUR = 8


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-day", type=int, default=3, help="Articles per day, on average.")
    parser.add_argument(
        "--start",
        type=lambda s: datetime.fromisoformat(s).replace(tzinfo=UTC),
        required=True,
        help="First publishing day, YYYY-MM-DD.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Read everything, grouped by topic, keeping file order so the editorial
    # sequence already chosen is preserved rather than reshuffled.
    files = sorted(DATA.glob("*.jsonl"))
    articles: list[tuple[Path, int, dict]] = []
    for path in files:
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            article = json.loads(line)
            # Only articles that carry a date are being scheduled. The earliest
            # batches were published outright and have none; giving them one
            # would put live articles back on a calendar they have already left.
            if not article.get("publish_at"):
                continue
            articles.append((path, index, article))

    order: list[str] = []
    groups: dict[str, list[dict]] = {}
    for _, _, article in articles:
        key = article.get("topic_key") or article["title"]
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(article)

    # Assign whole topics to days against a running target rather than filling
    # fixed slots. A topic is two articles, so a three-a-day cadence cannot be
    # met by any single day — it is met by alternating four and two. Tracking
    # the cumulative target lets the average come out right without ever
    # splitting a pair across a midnight.
    start = args.start.replace(hour=HOUR, minute=0, second=0, microsecond=0)
    schedule: dict[str, datetime] = {}
    offset = 0
    published = 0
    for key in order:
        # Move on when this day has already met its share of the running total.
        while published >= args.per_day * (offset + 1):
            offset += 1
        schedule[key] = start + timedelta(days=offset)
        published += len(groups[key])

    for key in order:
        when = schedule[key]
        for article in groups[key]:
            article["publish_at"] = when.isoformat().replace("+00:00", "Z")

    by_day: dict[str, int] = {}
    for key in order:
        stamp = schedule[key].strftime("%Y-%m-%d")
        by_day[stamp] = by_day.get(stamp, 0) + len(groups[key])

    print(f"{len(order)} topics, {sum(by_day.values())} articles")
    print(f"{min(by_day)} → {max(by_day)}  ({len(by_day)} publishing days)")
    counts = sorted(set(by_day.values()))
    print(f"articles per day: {counts}, mean {sum(by_day.values()) / len(by_day):.1f}")

    if args.dry_run:
        for stamp in sorted(by_day)[:8]:
            titles = [
                a["title"][:44]
                for k in order
                if schedule[k].strftime("%Y-%m-%d") == stamp
                for a in groups[k]
            ]
            print(f"  {stamp}  {len(titles)}  {titles[0]}…")
        return 0

    # Write back, preserving each file's original line order.
    for path in files:
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            article = json.loads(line)
            key = article.get("topic_key") or article["title"]
            if key in schedule:
                article["publish_at"] = schedule[key].isoformat().replace("+00:00", "Z")
            lines.append(json.dumps(article, ensure_ascii=False))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rewrote {len(files)} batch files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
