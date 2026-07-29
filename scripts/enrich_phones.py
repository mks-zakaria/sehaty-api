#!/usr/bin/env python
"""Fill in the phone numbers the listing pages withheld.

Neither directory puts a number on its category pages — the number is the thing
they are selling, so it lives one click deeper, on the practitioner's own page.
That means one request per doctor rather than one per twenty, which is why this
is a separate script with its own resume behaviour rather than part of the
harvest.

The number matters more than anything else collected. An address gets you to a
door; a number gets the visit booked without driving across Casablanca to find
the cabinet shut. It is also the single field that turns the printed pack into
something a secretary can act on.

Only the practitioner's own number is taken. Both sites also render their own
switchboard in the page furniture, and importing that would give several
thousand doctors the same wrong number — worse than having none, because it
looks right. So the label is matched, not the digit pattern.

Resumes: rows that already carry a number are skipped, so an interrupted run
costs nothing and re-running is free.

    uv run python scripts/enrich_phones.py --in scripts/data/casablanca.csv --dry-run
    uv run python scripts/enrich_phones.py --in scripts/data/casablanca.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

USER_AGENT = "SehatyDirectory/0.1 (+contact.agrilogy@gmail.com)"
RATE_LIMIT_SECONDS = 1.0
REQUEST_TIMEOUT = 25

# e-rdv labels the practitioner's line; its own switchboard sits in the footer
# with no label, so matching the label is what keeps them apart.
_ERDV_TEL = re.compile(r"<strong>\s*Tel:\s*</strong>\s*([0-9 .\-]{9,20})")
# Telecontact lists each line as an anchor whose first child is a "Tel 1:"
# label. Paying advertisers additionally get an itemprop="telephone" wrapper and
# everyone else does not, so keying on the wrapper found numbers for advertisers
# only — which is a small and badly-biased slice. The label is on both.
_TC_TEL = re.compile(r'href="tel:([0-9 .\-+()]{9,22})"[^>]*>\s*<label>\s*Tel')

_DIGITS = re.compile(r"\D+")

# Telecontact's sitemap is advertised in its robots.txt and lists every
# annonceur page. Their on-site search is Disallow'd, so this is the sanctioned
# way to find a practitioner who was never on the rubrique listing we walked.
SITEMAPS = [f"https://www.telecontact.ma/sitemap_annonceur_ville_{n}.xml" for n in range(1, 7)]
_SITEMAP_URL = re.compile(
    r"<loc>(https://www\.telecontact\.ma/annonceur/(.+?)/(\d+)/([a-z0-9-]+)\.php)</loc>"
)
# The page's own rubrique links, used to prove the name match is the same trade.
_RUBRIQUE = re.compile(r'href="/liens/([a-z0-9-]+)/')
RUBRIQUE_SPECIALTY = {
    "medecins-generalistes": "generalist",
    "medecin-generaliste": "generalist",
    "chirurgiens-dentistes": "dentistry",
    "chirurgien-dentiste": "dentistry",
    "dentiste": "dentistry",
    "cardiologues": "cardiology",
    "cardiologue": "cardiology",
    "dermatologues": "dermatology",
    "dermatologue": "dermatology",
    "gynecologues": "gynecology",
    "gynecologue": "gynecology",
    "ophtalmologues": "ophthalmology",
    "ophtalmologue": "ophthalmology",
    "pediatres": "pediatrics",
    "pediatre": "pediatrics",
    "psychiatres": "psychiatry",
    "psychiatre": "psychiatry",
    "orl": "otolaryngology",
    "chirurgiens-orthopedistes": "orthopedics",
    "chirurgien-orthopediste": "orthopedics",
    "orthopedistes": "orthopedics",
    "orthopediste": "orthopedics",
}


def normalise(raw: str) -> str | None:
    """Moroccan numbers to bare national form: 0522906302 / 0661445566.

    Returns None for anything that is not a plausible Moroccan landline or
    mobile — a half-scraped fragment is worse on a page than a blank field.
    """
    digits = _DIGITS.sub("", raw or "")
    if digits.startswith("212"):
        digits = "0" + digits[3:]
    if len(digits) != 10 or not digits.startswith("0") or digits[1] not in "5678":
        return None
    return digits


class Unreachable(Exception):
    """The page could not be fetched, after retrying.

    Distinct from "fetched, and there was no number on it" — and the distinction
    is the whole point. Collapsing both into None meant a throttled run looked
    exactly like a directory that publishes no phone numbers, and 587 doctors in
    Tanger were written off on that basis.
    """


# Sustained crawling gets throttled long before it gets blocked. Backing off and
# retrying recovers the run; treating the first refusal as an answer does not.
RETRIES = 3
BACKOFF_SECONDS = (5, 20, 60)


def fetch(url: str) -> str:
    """GET, retrying through a throttle. Raises Unreachable when it truly fails."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                body = response.read().decode("utf-8", "ignore")
            time.sleep(RATE_LIMIT_SECONDS)
            return body
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 404:
                # A missing page is an answer, not a failure to get one.
                time.sleep(RATE_LIMIT_SECONDS)
                raise Unreachable("404") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = exc
        # Back off further each time: the server is asking for room.
        time.sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])
    raise Unreachable(str(last))


def phones_from_erdv(url: str) -> list[str]:
    html = fetch(url)
    match = _ERDV_TEL.search(html)
    number = normalise(unescape(match.group(1))) if match else None
    return [number] if number else []


def phones_from_telecontact(url: str) -> list[str]:
    html = fetch(url)
    out: list[str] = []
    for raw in _TC_TEL.findall(html):
        number = normalise(unescape(raw))
        if number and number not in out:
            out.append(number)
    return out


def fold(text: str) -> str:
    """Compare names ignoring case, accents and punctuation.

    Telecontact slugs carry quirks — "outegda-saida-" keeps a trailing hyphen —
    so folding both sides to bare alphanumerics is what makes them comparable.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", ascii_only)


def fold_ville(city: str) -> str:
    """ "Dar Bouazza" -> "dar-bouazza", matching the sitemap's ville segment."""
    decomposed = unicodedata.normalize("NFKD", city.lower())
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-")


def build_sitemap_index(cache_dir: Path, villes: set[str]) -> dict[str, str]:
    """Folded practitioner name -> annonceur URL, for the towns we cover.

    Cached on disk: the six shards are ~60 MB in total and there is no reason to
    pull them again on a re-run.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    index: dict[str, str] = {}
    for number, url in enumerate(SITEMAPS, 1):
        path = cache_dir / f"sitemap_{number}.xml"
        if not path.exists() or path.stat().st_size < 1000:
            try:
                path.write_text(fetch(url), encoding="utf-8")
            except Unreachable:
                print(f"  ! sitemap {number} unavailable — skipped", file=sys.stderr)
                continue
        for full, slug, _id, ville in _SITEMAP_URL.findall(
            path.read_text(encoding="utf-8", errors="ignore")
        ):
            if ville in villes:
                # First wins: shards are ordered, and a duplicate name is a
                # coin flip we should not silently re-flip on every run.
                index.setdefault(fold(slug), full)
    return index


def phones_by_name(url: str, expect_specialty: str) -> tuple[list[str], str | None]:
    """Numbers from a name-matched page, but only if the trade matches.

    A name match alone is not identity: Casablanca has plumbers and pharmacies
    sharing surnames with doctors, and putting a plumber's line on a doctor's
    page is worse than leaving it blank. So the page has to categorise itself
    under the specialty we already believe, or nothing is taken from it.
    """
    html = fetch(url)
    found = {
        RUBRIQUE_SPECIALTY[slug] for slug in _RUBRIQUE.findall(html) if slug in RUBRIQUE_SPECIALTY
    }
    if not found:
        return [], "not-medical"
    if expect_specialty not in found:
        return [], "other-specialty"

    out: list[str] = []
    for raw in _TC_TEL.findall(html):
        number = normalise(unescape(raw))
        if number and number not in out:
            out.append(number)
    return out, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="path", required=True)
    parser.add_argument("--out", dest="out", default=None, help="defaults to in-place")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = every row")
    parser.add_argument(
        "--sitemap",
        action="store_true",
        help="second pass: look rows up in telecontact's sitemap by name",
    )
    parser.add_argument("--cache", default=".sitemap-cache")
    args = parser.parse_args()

    with open(args.path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0]) if rows else []

    todo = [r for r in rows if not r.get("phone_fixe") and not r.get("phone_mobile")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(rows)} rows, {len(todo)} without a number")

    index_by_name: dict[str, str] = {}
    if args.sitemap:
        villes = {fold_ville(r.get("city", "")) for r in rows if r.get("city")}
        villes |= {"casablanca"}
        index_by_name = build_sitemap_index(Path(args.cache), villes)
        print(f"sitemap index: {len(index_by_name)} names across {sorted(villes)}")

    found = 0
    rejected = {"not-medical": 0, "other-specialty": 0, "no-match": 0}
    # Counted separately from "no number on the page". Conflating them is what
    # made a throttled Tanger run look like a source with nothing to give.
    unreachable = 0
    for index, row in enumerate(todo, 1):
        source, url = row.get("source", ""), row.get("source_url", "")

        try:
            if args.sitemap:
                # Second pass: this row's own directory published no number, so
                # look the person up on telecontact by name instead.
                match = index_by_name.get(fold(row.get("source_name", "")))
                if not match:
                    rejected["no-match"] += 1
                    numbers = []
                else:
                    numbers, why = phones_by_name(match, row.get("specialty", ""))
                    if why:
                        rejected[why] += 1
            elif not url:
                continue
            elif "e-rdv" in source:
                numbers = phones_from_erdv(url)
            elif "telecontact" in source:
                numbers = phones_from_telecontact(url)
            else:
                numbers = []
        except Unreachable:
            unreachable += 1
            numbers = []

        if numbers:
            found += 1
            # 06/07 are mobile in Morocco, 05 is a landline. The split is not
            # cosmetic: it decides whether the WhatsApp confirmation ask is even
            # possible for that cabinet.
            for number in numbers:
                key = "phone_mobile" if number[1] in "67" else "phone_fixe"
                if not row.get(key):
                    row[key] = number
            # whatsapp is deliberately NOT filled from the mobile. Most
            # Moroccan mobiles are on WhatsApp, but "most" puts a dead button on
            # the pages of the ones that are not — and the page renders that
            # button as a promise. It is a yes/no question worth ten seconds on
            # the visit, so it stays empty until someone has asked.
        if index % 100 == 0:
            note = f" ({unreachable} unreachable)" if unreachable else ""
            print(f"  {index}/{len(todo)} — {found} numbers so far{note}", flush=True)

    print(f"found {found} of {len(todo)} ({found * 100 // max(len(todo), 1)}%)")
    if unreachable:
        # Loudly, because these are recoverable: re-running skips the rows that
        # already have a number and retries only these.
        print(
            f"  ! {unreachable} pages unreachable — those doctors have no number "
            f"*yet*. Re-run to retry only them.",
            file=sys.stderr,
        )
    if args.sitemap:
        # Say what was refused and why. A silent rejection is indistinguishable
        # from a source with no numbers, which is how the first two attempts at
        # this looked like an empty directory rather than a broken lookup.
        print(
            f"  no name in sitemap  : {rejected['no-match']}\n"
            f"  page not a medic    : {rejected['not-medical']}\n"
            f"  different specialty : {rejected['other-specialty']}"
        )

    if args.dry_run:
        print("[dry-run] nothing written")
        return 0

    target = args.out or args.path
    with open(target, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
