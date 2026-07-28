#!/usr/bin/env python
"""Blank any published address that contains markup instead of an address.

A scraper bug put the star-rating widget into 374 imported addresses — text
reading ``☆ ☆ ☆ ☆ ☆ (0 avis) <div class=...`` on real practitioners' public
pages. Re-importing the corrected harvest repaired most of them, but not all:
a doctor who appeared in the broken run and not in the corrected one is never
matched by the importer, so their bad row simply stays.

Hence a sweep that works from the database rather than from a CSV. It blanks
rather than guesses: an empty address renders a shorter page, and a shorter
page is strictly better than a person's listing with markup on it.

    uv run python scripts/repair_addresses.py --dry-run
    uv run python scripts/repair_addresses.py
"""

from __future__ import annotations

import argparse
import re
import sys

from sehaty.core.db.session import get_session
from sehaty.db import DoctorProfile
from sqlalchemy import select

# Anything here means the value came from a page, not from a person.
JUNK = re.compile(r"<|>|☆|\(\d+\s*avis\)|class=|href=|&[a-z]+;|https?://")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with get_session() as session:
        rows = list(
            session.execute(
                select(DoctorProfile.user_id, DoctorProfile.full_name, DoctorProfile.address).where(
                    DoctorProfile.address.is_not(None)
                )
            ).all()
        )

    broken = [r for r in rows if JUNK.search(r.address or "")]
    print(f"{len(rows)} profiles with an address, {len(broken)} broken")
    for row in broken[:20]:
        print(f"  {row.user_id:5} {row.full_name[:34]:36} {row.address[:52]}")
    if len(broken) > 20:
        print(f"  … and {len(broken) - 20} more")

    if args.dry_run or not broken:
        print("[dry-run] nothing written" if args.dry_run else "nothing to do")
        return 0

    with get_session() as session:
        for row in broken:
            session.get(DoctorProfile, row.user_id).address = None
        session.flush()
    print(f"blanked {len(broken)} addresses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
