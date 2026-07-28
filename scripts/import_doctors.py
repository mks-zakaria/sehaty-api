#!/usr/bin/env python
"""Bulk-import doctors from a CSV into published, unclaimed landing pages.

The point of this script is the sales conversation: a doctor who lands on
`/casablanca/dentiste` and sees forty colleagues believes the platform; one who
sees three does not. So the map gets filled from public professional directory
data before anyone is visited, and each imported doctor gets a real page with a
"vous êtes ce médecin ?" banner and a removal link.

Usage:
    cd sehaty-api
    uv run python scripts/import_doctors.py doctors.csv --dry-run
    uv run python scripts/import_doctors.py doctors.csv

CSV columns (header row required). Only `full_name` and `specialty` are
mandatory; everything else is filled in on the visit:

    full_name,specialty,city,district,address,phone_fixe,phone_mobile,
    whatsapp,lat,lng,license_no,consultation_fee,languages,insurances,hours

  * `specialty`  — a specialty **slug** that must already exist (`dentistry`,
                   `cardiology`, …). Unknown slugs are reported, not invented.
  * `languages`  — pipe-separated: `fr|ar|ary`.
  * `insurances` — pipe-separated payer slugs: `cnss|cnops|amo`.
  * `hours`      — compact weekly form, semicolons between days:
                   `1:09:00-12:30,15:00-19:00; 6:09:00-13:00`
                   where the leading digit is 1=Monday … 7=Sunday. A day that
                   is absent is closed. Malformed entries fail the row rather
                   than publishing wrong opening times.
  * `lat`/`lng`  — decimal degrees; both or neither.

Guarantees that matter:

  * **Idempotent.** Re-running updates existing rows instead of duplicating
    them, matched on the generated slug. Field sales means running this many
    times as the sheet improves.
  * **Never republishes a removal.** A doctor whose page was delisted at their
    request (`claim_status = REMOVAL_REQUESTED`) is skipped, permanently. This
    is the whole reason removals are a tombstone rather than a delete.
  * **Never overwrites a real doctor's own edits.** Rows that are CLAIMED or
    VERIFIED are left untouched — an import must not clobber what a paying
    doctor typed about themselves.
  * **Never claims verification.** Imported pages are LISTED: public and
    searchable, with no "Vérifié" badge. That badge means a human checked a
    licence, and an import has met nobody.
  * **No invented data.** Missing photo, hours, fee and insurance stay empty;
    the page renders shorter. Fabricating a plausible opening time would put
    wrong information on a real professional's public listing.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sehaty.core.places import place_slug
from sehaty.db import (
    ClaimStatus,
    DoctorProfile,
    DoctorSpecialty,
    ProfileSource,
    Specialty,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

_SRID = 4326
# Imported doctors have no login. A synthetic, non-routable address keeps the
# NOT NULL/unique constraint satisfied without implying we can email them —
# and makes it obvious in the DB that nobody has signed up yet.
_PLACEHOLDER_EMAIL_DOMAIN = "import.invalid"
# A value carrying markup is not something a person wrote — see the guard below.
_MARKUP = re.compile(r"<|>|☆|\(\d+\s*avis\)|class=|href=|&[a-z]+;|https?://")
# Zero-padded 24h times, matching what the model and the page expect.
_HHMM = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@dataclass
class Stats:
    created: int = 0
    updated: int = 0
    skipped_removed: int = 0
    skipped_claimed: int = 0
    errors: list[str] = field(default_factory=list)

    def report(self, *, dry_run: bool) -> str:
        prefix = "[dry-run] would " if dry_run else ""
        lines = [
            f"{prefix}create : {self.created}",
            f"{prefix}update : {self.updated}",
            f"skipped (removal requested): {self.skipped_removed}",
            f"skipped (claimed by doctor): {self.skipped_claimed}",
        ]
        if self.errors:
            lines.append(f"errors : {len(self.errors)}")
            lines.extend(f"  - {e}" for e in self.errors)
        return "\n".join(lines)


def doctor_slug(full_name: str, city: str | None) -> str:
    """Stable, readable slug: ``dr-amina-bennani-casablanca``.

    The city is part of the slug because two doctors sharing a name in different
    cities is far more likely than in the same one, and a slug is a printed QR
    target — it must never be reassigned once a plaque exists.
    """
    decomposed = unicodedata.normalize("NFKD", full_name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    parts = [place_slug(ascii_name)]
    if city:
        parts.append(place_slug(city))
    return "-".join(p for p in parts if p)


def _parse_hours(value: str | None, row_no: int) -> list[dict] | None:
    """Parse the compact `1:09:00-12:30,15:00-19:00; 6:09:00-13:00` form.

    Returns None for a blank cell so the column stays optional. Anything
    malformed raises: wrong opening hours on a public page send patients to a
    closed door, which is worse than showing none.
    """
    cleaned = _clean(value)
    if cleaned is None:
        return None

    out: list[dict] = []
    for chunk in cleaned.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        day, _, spans = chunk.partition(":")
        if not spans or not day.strip().isdigit():
            raise ValueError(f"row {row_no}: bad hours entry {chunk!r}")
        weekday = int(day.strip()) - 1  # sheet is 1=Monday; storage is 0=Monday
        if not 0 <= weekday <= 6:
            raise ValueError(f"row {row_no}: weekday must be 1-7, got {day!r}")

        ranges: list[list[str]] = []
        for span in spans.split(","):
            start, sep, end = span.strip().partition("-")
            if not sep:
                raise ValueError(f"row {row_no}: bad time range {span!r}")
            start, end = start.strip(), end.strip()
            # Times are validated here, not downstream: the importer writes
            # straight to the model, so a malformed "0900" would otherwise land
            # in the database and break the page's hours and its JSON-LD.
            for value in (start, end):
                if not _HHMM.fullmatch(value):
                    raise ValueError(f"row {row_no}: time must be HH:MM, got {value!r}")
            if start >= end:
                raise ValueError(f"row {row_no}: range start must precede end: {span!r}")
            ranges.append([start, end])
        if ranges:
            out.append({"weekday": weekday, "ranges": ranges})

    return sorted(out, key=lambda e: e["weekday"])


def _clean(value: str | None) -> str | None:
    """Trim, and treat blank cells as absent rather than as empty strings."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _parse_float(value: str | None, label: str, row_no: int) -> float | None:
    cleaned = _clean(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"row {row_no}: {label} is not a number: {cleaned!r}") from exc


def _unique_slug(session: Session, base: str, user_id: int | None) -> str:
    """``base``, or ``base-2``/``base-3`` when another doctor already holds it."""
    candidate = base
    suffix = 1
    while True:
        owner = session.execute(
            select(DoctorProfile.user_id).where(DoctorProfile.slug == candidate)
        ).scalar_one_or_none()
        if owner is None or owner == user_id:
            return candidate
        suffix += 1
        candidate = f"{base}-{suffix}"


def import_row(
    session: Session,
    row: dict[str, str],
    row_no: int,
    specialties: dict[str, int],
    stats: Stats,
    *,
    dry_run: bool,
) -> None:
    full_name = _clean(row.get("full_name"))
    if not full_name:
        raise ValueError(f"row {row_no}: full_name is required")

    specialty_slug = _clean(row.get("specialty"))
    if not specialty_slug:
        raise ValueError(f"row {row_no}: specialty is required")
    if specialty_slug not in specialties:
        # Reported, never invented: a made-up specialty would put a doctor on
        # the wrong browse page.
        raise ValueError(f"row {row_no}: unknown specialty slug {specialty_slug!r}")

    # A scraper once fed the star-rating widget in as an address and published
    # "☆ ☆ ☆ ☆ ☆ (0 avis) <div class=..." on 374 real practitioners' pages.
    # The boundary is the right place to refuse that: whatever generates the CSV
    # next, a value carrying markup is not an address anyone wrote.
    for column in ("full_name", "address", "district", "city"):
        value = _clean(row.get(column)) or ""
        if _MARKUP.search(value):
            raise ValueError(f"row {row_no}: {column} contains markup: {value[:40]!r}")

    city = _clean(row.get("city"))
    lat = _parse_float(row.get("lat"), "lat", row_no)
    lng = _parse_float(row.get("lng"), "lng", row_no)
    if (lat is None) != (lng is None):
        raise ValueError(f"row {row_no}: lat and lng must be given together")

    base_slug = doctor_slug(full_name, city)
    existing = session.execute(
        select(DoctorProfile).where(DoctorProfile.slug == base_slug)
    ).scalar_one_or_none()

    if existing is not None:
        if existing.claim_status == ClaimStatus.REMOVAL_REQUESTED:
            # The tombstone. Never put this doctor back online.
            stats.skipped_removed += 1
            return
        if existing.claim_status in (ClaimStatus.CLAIMED, ClaimStatus.VERIFIED):
            # Their own edits outrank the spreadsheet.
            stats.skipped_claimed += 1
            return

    languages = [
        code.strip().lower()
        for code in (_clean(row.get("languages")) or "").split("|")
        if code.strip()
    ]
    fields = {
        "full_name": full_name,
        "city": city,
        "district": _clean(row.get("district")),
        "address": _clean(row.get("address")),
        "phone_fixe": _clean(row.get("phone_fixe")),
        "phone_mobile": _clean(row.get("phone_mobile")),
        "whatsapp": _clean(row.get("whatsapp")),
        "consultation_fee": _parse_float(row.get("consultation_fee"), "consultation_fee", row_no),
        "languages": languages,
    }
    # Optional columns: only written when the sheet actually carries them, so a
    # re-import from a thinner CSV never blanks hours somebody typed by hand.
    insurances = [
        code.strip().lower()
        for code in (_clean(row.get("insurances")) or "").split("|")
        if code.strip()
    ]
    if insurances:
        fields["insurances"] = insurances
    hours = _parse_hours(row.get("hours"), row_no)
    if hours is not None:
        fields["opening_hours"] = hours

    if dry_run:
        stats.updated += 1 if existing else 0
        stats.created += 0 if existing else 1
        return

    if existing is None:
        user = User(
            email=f"{base_slug}@{_PLACEHOLDER_EMAIL_DOMAIN}",
            role=UserRole.DOCTOR,
            is_active=True,
        )
        session.add(user)
        session.flush()
        profile = DoctorProfile(
            user_id=user.id,
            slug=_unique_slug(session, base_slug, user.id),
            license_no=_clean(row.get("license_no")) or f"IMPORT-{user.id}",
            # Published so the page is live and the city listing is populated;
            # the banner makes its unclaimed status plain on the page itself.
            # LISTED, never VERIFIED: the page is compiled from a public
            # directory, which makes it legitimate to publish and says nothing
            # about a licence anyone checked. Marking these VERIFIED — which an
            # earlier version did, because the public read accepted nothing
            # else — badged thousands of doctors nobody had ever spoken to.
            verification_status=VerificationStatus.LISTED,
            claim_status=ClaimStatus.UNCLAIMED,
            source=ProfileSource.IMPORT,
            **fields,
        )
        session.add(profile)
        session.flush()
        stats.created += 1
    else:
        profile = existing
        for key, value in fields.items():
            setattr(profile, key, value)
        stats.updated += 1

    if lat is not None and lng is not None:
        profile.geopoint = WKTElement(f"POINT({lng} {lat})", srid=_SRID)

    specialty_id = specialties[specialty_slug]
    already = session.execute(
        select(DoctorSpecialty).where(
            DoctorSpecialty.doctor_id == profile.user_id,
            DoctorSpecialty.specialty_id == specialty_id,
        )
    ).scalar_one_or_none()
    if already is None:
        session.add(DoctorSpecialty(doctor_id=profile.user_id, specialty_id=specialty_id))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path, help="CSV file to import")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate without writing anything.",
    )
    args = parser.parse_args()

    if not args.csv_path.is_file():
        print(f"no such file: {args.csv_path}", file=sys.stderr)
        return 2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    stats = Stats()

    with args.csv_path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    with factory() as session:
        specialties = {
            slug: sid for slug, sid in session.execute(select(Specialty.slug, Specialty.id)).all()
        }
        if not specialties:
            print(
                "no specialties in the database — seed the catalogue first",
                file=sys.stderr,
            )
            return 2

        for row_no, row in enumerate(rows, start=2):  # row 1 is the header
            try:
                import_row(session, row, row_no, specialties, stats, dry_run=args.dry_run)
            except ValueError as exc:
                stats.errors.append(str(exc))

        if args.dry_run:
            session.rollback()
        else:
            session.commit()

    print(stats.report(dry_run=args.dry_run))
    # A row that failed to parse is a data problem the operator must see, so it
    # fails the run rather than being buried in the summary.
    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
