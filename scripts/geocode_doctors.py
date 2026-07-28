#!/usr/bin/env python
"""Put imported doctors on the map, honestly.

A doctor with no coordinates is invisible to "près de chez moi", which is most
of what the free page is worth to them. Imported pages arrive with a written
address and nothing else, so something has to turn that into a point.

The catch is that Moroccan cabinet addresses are lotissement-and-block
references — "Madinat Errahma, bloc U4, n°107" — and no map database holds
them. OpenStreetMap resolves the *town* and nothing finer. So the point that
comes back is the quartier, not the door, and every doctor in Errahma lands on
the same pin.

That is genuinely useful and genuinely limited, so it is recorded rather than
glossed: each row is stamped ``geo_precision``. APPROXIMATE points place a
cabinet in the right neighbourhood for search; the public page knows not to
build turn-by-turn directions from them, and falls back to the written address.
Confidently driving a patient to a centroid would be worse than not having a
pin at all.

Usage:
    uv run python scripts/geocode_doctors.py --dry-run
    uv run python scripts/geocode_doctors.py
    uv run python scripts/geocode_doctors.py --city Casablanca --limit 50
    # undo a pin dropped at the wrong address, one doctor at a time:
    uv run python scripts/geocode_doctors.py --doctor 31 --force

Nominatim's usage policy allows this volume with a real User-Agent and at most
one request a second; both are enforced below rather than left to the caller.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

from geoalchemy2.elements import WKTElement
from sehaty.core.db.session import get_session
from sehaty.db import DoctorProfile, GeoPrecision
from sqlalchemy import select

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# Nominatim requires a contactable identity; anonymous bulk use gets blocked.
USER_AGENT = os.environ.get("SEHATY_GEOCODER_UA", "SehatyDirectory/0.1 (contact@sehaty.ma)")
# Their policy is one request per second. 1.1 leaves room for clock jitter.
RATE_LIMIT_SECONDS = 1.1

# A result no more specific than these is a neighbourhood, not an address.
_APPROXIMATE_TYPES = {
    "town",
    "city",
    "village",
    "suburb",
    "neighbourhood",
    "quarter",
    "municipality",
    "administrative",
    "postcode",
    "post_office",
}


@dataclass
class Located:
    lat: float
    lng: float
    precision: GeoPrecision
    matched: str


def _query(text: str) -> dict | None:
    url = f"{NOMINATIM}?{urllib.parse.urlencode({'format': 'json', 'limit': 1, 'q': text})}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=20) as response:
        results = json.load(response)
    return results[0] if results else None


def _candidates(profile: DoctorProfile) -> list[str]:
    """Progressively coarser queries: exact address first, quartier last.

    Ordered so a lucky precise hit is preferred, and the coarse fallback only
    runs when nothing finer exists — which, for these addresses, is usually.
    """
    city = profile.city or "Casablanca"
    out: list[str] = []
    if profile.address:
        out.append(f"{profile.address}, {city}, Morocco")
    if profile.district:
        out.append(f"{profile.district}, {city}, Morocco")
    out.append(f"{city}, Morocco")
    return out


def locate(profile: DoctorProfile) -> Located | None:
    """First query that returns anything, with its precision recorded."""
    for index, text in enumerate(_candidates(profile)):
        result = _query(text)
        time.sleep(RATE_LIMIT_SECONDS)
        if not result:
            continue
        # Anything but a first-attempt, non-place-type hit is a neighbourhood.
        coarse = index > 0 or result.get("type") in _APPROXIMATE_TYPES
        return Located(
            lat=float(result["lat"]),
            lng=float(result["lon"]),
            precision=GeoPrecision.APPROXIMATE if coarse else GeoPrecision.EXACT,
            matched=result.get("display_name", "")[:70],
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="resolve but do not write")
    parser.add_argument("--city", default=None, help="only this city")
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument(
        "--doctor",
        type=int,
        default=None,
        help="only this doctor id; with --force, re-geocodes it whatever it holds",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an EXACT pin — for undoing one dropped by mistake",
    )
    parser.add_argument(
        "--regeocode",
        action="store_true",
        help="also revisit rows that already have a point (never touches EXACT)",
    )
    args = parser.parse_args()

    with get_session() as session:
        stmt = select(DoctorProfile).limit(args.limit)
        if args.city:
            stmt = stmt.where(DoctorProfile.city == args.city)
        if args.doctor:
            stmt = stmt.where(DoctorProfile.user_id == args.doctor)
        profiles = list(session.execute(stmt).scalars())

    todo = []
    for profile in profiles:
        if args.force and args.doctor:
            # Deliberate, one doctor at a time: the way to undo a pin dropped at
            # the wrong address. Refusing to scope it means nobody can ever
            # correct a mistake, which is worse than the risk of this flag.
            todo.append(profile)
        elif profile.geopoint is None:
            todo.append(profile)
        elif args.regeocode and profile.geo_precision == GeoPrecision.APPROXIMATE:
            # A hand-placed or self-entered EXACT point is better than anything
            # this script can produce, so it is never overwritten.
            todo.append(profile)

    print(f"{len(profiles)} profiles, {len(todo)} to geocode")

    located = exact = approximate = failed = 0
    for profile in todo:
        found = locate(profile)
        if found is None:
            failed += 1
            print(f"  ✗ {profile.full_name[:38]:40} no match")
            continue

        located += 1
        if found.precision == GeoPrecision.EXACT:
            exact += 1
        else:
            approximate += 1
        mark = "≈" if found.precision == GeoPrecision.APPROXIMATE else "="
        print(
            f"  {mark} {profile.full_name[:38]:40} {found.lat:.5f},{found.lng:.5f}  {found.matched}"
        )

        if args.dry_run:
            continue
        with get_session() as session:
            row = session.get(DoctorProfile, profile.user_id)
            row.geopoint = WKTElement(f"POINT({found.lng} {found.lat})", srid=4326)
            row.geo_precision = found.precision
            session.flush()

    prefix = "[dry-run] " if args.dry_run else ""
    print(
        f"{prefix}located {located} ({exact} exact, {approximate} approximate), {failed} unmatched"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
