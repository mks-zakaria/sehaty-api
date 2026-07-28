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
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

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


def fetch(url: str) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8", "ignore")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    finally:
        time.sleep(RATE_LIMIT_SECONDS)


def phones_from_erdv(url: str) -> list[str]:
    html = fetch(url)
    if not html:
        return []
    match = _ERDV_TEL.search(html)
    number = normalise(unescape(match.group(1))) if match else None
    return [number] if number else []


def phones_from_telecontact(url: str) -> list[str]:
    html = fetch(url)
    if not html:
        return []
    out: list[str] = []
    for raw in _TC_TEL.findall(html):
        number = normalise(unescape(raw))
        if number and number not in out:
            out.append(number)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="path", required=True)
    parser.add_argument("--out", dest="out", default=None, help="defaults to in-place")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="0 = every row")
    args = parser.parse_args()

    with open(args.path, newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
        columns = list(rows[0]) if rows else []

    todo = [r for r in rows if not r.get("phone_fixe") and not r.get("phone_mobile")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(rows)} rows, {len(todo)} without a number")

    found = 0
    for index, row in enumerate(todo, 1):
        source, url = row.get("source", ""), row.get("source_url", "")
        if not url:
            continue
        if "e-rdv" in source:
            numbers = phones_from_erdv(url)
        elif "telecontact" in source:
            numbers = phones_from_telecontact(url)
        else:
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
            print(f"  {index}/{len(todo)} — {found} numbers so far", flush=True)

    print(f"found {found} of {len(todo)} ({found * 100 // max(len(todo), 1)}%)")

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
