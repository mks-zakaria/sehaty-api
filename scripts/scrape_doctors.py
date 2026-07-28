#!/usr/bin/env python
"""Harvest public doctor listings into an importer-ready CSV.

The map only sells the platform once it is dense: a doctor who lands on
`/casablanca/dentiste` and sees forty colleagues believes it, one who sees three
does not. This walks the public directory listings and writes the same CSV shape
`import_doctors.py` already consumes.

Two sources, deliberately different in character:

* **telecontact** — the Moroccan yellow pages, whose whole purpose is publishing
  business contact details, and whose robots.txt leaves these listing paths open
  to a generic agent. Best provenance, but it serves at most twenty entries per
  rubrique for a large city and its pagination does not advance, so it can only
  ever cover the surface plus the small surrounding communes in full.
* **erdv** — a booking directory that does paginate, and therefore the only
  place the Casablanca long tail is reachable. It is also a competitor, so this
  source is opt-in per run rather than a default.

Nothing is invented. A field the listing does not publish is left empty and the
page renders shorter; neither source exposes phone numbers on its listing pages,
so those stay blank and are collected on the visit.

Politeness is enforced here rather than left to the caller: one request a second,
a contactable User-Agent, and a hard page ceiling per specialty.

Usage:
    uv run python scripts/scrape_doctors.py --source telecontact --out casa.csv
    uv run python scripts/scrape_doctors.py --source erdv --max-pages 90 --out casa.csv
    uv run python scripts/scrape_doctors.py --source both --out casa.csv
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
from dataclasses import dataclass, field
from html import unescape

USER_AGENT = "SehatyDirectory/0.1 (+contact.agrilogy@gmail.com)"
RATE_LIMIT_SECONDS = 1.0
REQUEST_TIMEOUT = 25

# Our specialty slug -> the rubrique each source files it under.
SPECIALTIES: dict[str, dict[str, str]] = {
    "generalist": {"tc": "medecins-generalistes", "erdv": "medecins-generalistes"},
    "dentistry": {"tc": "chirurgiens-dentistes", "erdv": "chirurgiens-dentistes"},
    "cardiology": {"tc": "cardiologues", "erdv": "cardiologues"},
    "dermatology": {"tc": "dermatologues", "erdv": "dermatologues"},
    "gynecology": {"tc": "gynecologues", "erdv": "gynecologues"},
    "ophthalmology": {"tc": "ophtalmologues", "erdv": "ophtalmologues"},
    "pediatrics": {"tc": "pediatres", "erdv": "pediatres"},
    "psychiatry": {"tc": "psychiatres", "erdv": "psychiatres"},
    "otolaryngology": {"tc": "orl", "erdv": "oto-rhino-laryngologistes"},
    "orthopedics": {"tc": "chirurgiens-orthopedistes", "erdv": "chirurgiens-orthopedistes"},
}

# Telecontact serves complete sets for these; Casablanca itself is capped at 20.
TC_VILLES = [
    "casablanca",
    "dar-bouazza",
    "bouskoura",
    "mohammedia",
    "mediouna",
    "tit-mellil",
    "ain-harrouda",
]

# Quartier names that appear inside written addresses, most specific first so
# "Sidi Maârouf" is not swallowed by a bare "Sidi".
DISTRICTS = [
    "Madinat Errahma",
    "Madinat Arrahma",
    "Madinate Arrahma",
    "Jaouharat Errahma",
    "Bassatine Errahma",
    "Errahma",
    "Arrahma",
    "Rahma",
    "Sidi Maârouf",
    "Sidi Maarouf",
    "Sidi Bernoussi",
    "Sidi Moumen",
    "Sidi Belyout",
    "Hay Hassani",
    "Hay Mohammadi",
    "Ain Chock",
    "Ain Sebaâ",
    "Ain Sebaa",
    "Ain Diab",
    "Mers Sultan",
    "Derb Sultan",
    "Ben M'sick",
    "Moulay Rachid",
    "Roches Noires",
    "Bourgogne",
    "Gauthier",
    "Racine",
    "Maârif",
    "Maarif",
    "Anfa",
    "Oulfa",
    "Lissasfa",
    "Sbata",
    "El Fida",
    "Californie",
    "Bouskoura",
    "Dar Bouazza",
]


@dataclass
class Listing:
    full_name: str
    specialty: str
    city: str
    district: str = ""
    address: str = ""
    source: str = ""
    source_name: str = ""
    source_id: str = ""
    # The listing's own link to the practitioner page. Captured rather than
    # rebuilt from the name: telecontact slugs carry quirks a reconstruction
    # cannot guess ("outegda-saida-" keeps a trailing hyphen), and a wrong URL
    # silently yields no phone rather than an error.
    source_url: str = ""


@dataclass
class Stats:
    pages: int = 0
    rows: int = 0
    by_specialty: dict[str, int] = field(default_factory=dict)


def fetch(url: str) -> str | None:
    """GET with the identifying agent, or None when the page does not exist."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            return response.read().decode("utf-8", "ignore")
    except urllib.error.HTTPError:
        return None
    except (urllib.error.URLError, TimeoutError):
        return None
    finally:
        time.sleep(RATE_LIMIT_SECONDS)


def strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def find_district(address: str) -> str:
    lowered = address.lower()
    for name in DISTRICTS:
        if name.lower() in lowered:
            return name
    return ""


def display_name(raw: str) -> str:
    """Directories list SURNAME Firstname; a public page needs it the other way.

    Practices keep their own name — "Centre Dentaire Errahma" is not a person
    and must not be re-ordered into one.
    """
    raw = raw.strip(" .,")
    words = raw.split()
    if not words:
        return raw
    if words[0].lower() in {"centre", "cabinet", "clinique", "polyclinique", "laboratoire"}:
        return raw
    if len(words) == 1:
        return f"Dr {raw}"
    *surname, first = words
    return f"Dr {first} {' '.join(surname)}"


# --- telecontact ----------------------------------------------------------

# Telecontact marks up each listing as schema.org/LocalBusiness. Splitting on
# the item wrapper and reading itemprop is the difference between an address and
# whatever text happened to follow the link — the first version of this scraper
# grabbed the star-rating widget for all 374 rows.
# Listings come in three flavours of wrapper class (-entreprise, -profession,
# -non-annonceur). They share the schema.org itemtype, so split on that rather
# than on any one class and silently miss two thirds of the page.
_TC_ITEM = re.compile(r"schema\.org/LocalBusiness([\s\S]*?)(?=schema\.org/LocalBusiness|\Z)")
_TC_ID = re.compile(r'data-id="(\d+)"\s+data-value="([^"]*)"')
_TC_STREET = re.compile(r'itemprop="streetAddress"[^>]*>([^<]+)<')
_TC_HREF = re.compile(r'href="(/annonceur/[^"]+\.php)\s*"')


def scrape_telecontact(specialty: str, ville: str) -> list[Listing]:
    rubrique = SPECIALTIES[specialty]["tc"]
    html = fetch(f"https://www.telecontact.ma/liens/{rubrique}/{ville}.php")
    if not html or "Inaccessibilit" in html:
        return []

    out: list[Listing] = []
    seen: set[str] = set()
    for block in _TC_ITEM.findall(html):
        id_match = _TC_ID.search(block)
        if not id_match:
            continue
        listing_id, name = id_match.group(1), unescape(id_match.group(2)).strip()
        if listing_id in seen or len(name) < 3:
            continue
        seen.add(listing_id)

        # Telecontact files labs and pharmacies under clinical rubriques; they
        # are real businesses but they are not the doctor this row claims to be.
        if re.match(r"(laboratoire|pharmacie|opticien|parapharmacie)\b", name, re.I):
            continue

        street = _TC_STREET.search(block)
        address = unescape(street.group(1)).strip() if street else ""
        # The block repeats "<postcode> <city> Maroc"; the street is what is left.
        address = re.sub(r"\s*\d{5}\s+[A-Za-zÀ-ÿ' -]+\s+Maroc\s*$", "", address).strip(" .,-")
        if "<" in address or "☆" in address:
            # Refuse rather than publish markup on a real person's page.
            address = ""

        out.append(
            Listing(
                full_name=display_name(name),
                specialty=specialty,
                city="Casablanca" if ville == "casablanca" else ville.replace("-", " ").title(),
                district=find_district(address)
                or ("" if ville == "casablanca" else ville.replace("-", " ").title()),
                address=address,
                source="telecontact.ma",
                source_name=name,
                source_id=listing_id,
                source_url=(
                    "https://www.telecontact.ma" + href.group(1).strip()
                    if (href := _TC_HREF.search(block))
                    else ""
                ),
            )
        )
    return out


# --- e-rdv ----------------------------------------------------------------

_ERDV_BLOCK = re.compile(
    r'<div class="col fiche">([\s\S]*?)(?=<div class="col fiche">|<div class="row line-search|\Z)'
)
_ERDV_NAME = re.compile(r'data-id="MA(\d+)"\s+data-value="([^"]+)"')
_ERDV_HREF = re.compile(r'href="(https://www\.e-rdv\.ma/rdv/[^"]+\.html)"')
_ERDV_ADDR = re.compile(
    r'<p style="font-size:14px;padding-top: 5px;padding-left: 6px;">([\s\S]{0,300}?)<strong>'
)


def scrape_erdv_page(specialty: str, city: str, page: int) -> list[Listing]:
    rubrique = SPECIALTIES[specialty]["erdv"]
    query = urllib.parse.urlencode({"quoi": rubrique, "ville": city, "page": page})
    html = fetch(f"https://www.e-rdv.ma/resultats-sante.php?{query}")
    if not html:
        return []

    out: list[Listing] = []
    for block in _ERDV_BLOCK.findall(html):
        name_match = _ERDV_NAME.search(block)
        if not name_match:
            continue
        listing_id, name = name_match.group(1), name_match.group(2).strip()
        address_match = _ERDV_ADDR.search(block)
        address = strip_tags(address_match.group(1)) if address_match else ""
        # The listing repeats the city inside the address; drop the tail.
        address = re.sub(r"[-,\s]*" + re.escape(city) + r"\s*$", "", address, flags=re.I).strip()
        out.append(
            Listing(
                full_name=display_name(name),
                specialty=specialty,
                city=city.title(),
                district=find_district(address),
                address=address,
                source="e-rdv.ma",
                source_name=name,
                source_id=listing_id,
                source_url=(m.group(1) if (m := _ERDV_HREF.search(block)) else ""),
            )
        )
    return out


def scrape_erdv(specialty: str, city: str, max_pages: int, stats: Stats) -> list[Listing]:
    """Walk pages until one comes back empty, or the ceiling is reached.

    The ceiling is reported rather than silently applied: a run that stopped
    early because of it has not covered the specialty, and saying so is the
    difference between a partial list and a list believed to be complete.
    """
    out: list[Listing] = []
    for page in range(1, max_pages + 1):
        rows = scrape_erdv_page(specialty, city, page)
        stats.pages += 1
        if not rows:
            return out
        out.extend(rows)
        if page == max_pages:
            print(
                f"    ! {specialty}: stopped at the {max_pages}-page ceiling — there may be more",
                file=sys.stderr,
            )
    return out


# --- assembly -------------------------------------------------------------

COLUMNS = [
    "full_name",
    "specialty",
    "city",
    "district",
    "address",
    "phone_fixe",
    "phone_mobile",
    "whatsapp",
    "lat",
    "lng",
    "license_no",
    "consultation_fee",
    "languages",
    "insurances",
    "hours",
    "source_name",
    "source",
    # The listing id, kept so enrich_phones can build the practitioner's own
    # page URL later. Neither directory publishes a number on its category
    # pages, so the number always costs a second request.
    "source_id",
    "source_url",
]


def dedupe(listings: list[Listing]) -> list[Listing]:
    """One row per person per specialty.

    The same doctor is listed by both sources and sometimes twice by one, so the
    key is the folded name plus specialty rather than the source id — ids differ
    between directories for the same human.
    """
    out: dict[tuple[str, str], Listing] = {}
    for item in listings:
        folded = "".join(
            c
            for c in unicodedata.normalize("NFKD", item.full_name.lower())
            if not unicodedata.combining(c)
        )
        folded = re.sub(r"[^a-z0-9]+", "", folded)
        key = (folded, item.specialty)
        existing = out.get(key)
        # Prefer the record that actually carries an address.
        if existing is None or (not existing.address and item.address):
            out[key] = item
    return list(out.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=("telecontact", "erdv", "both"), default="telecontact")
    parser.add_argument("--city", default="casablanca")
    parser.add_argument("--out", default="doctors-scraped.csv")
    parser.add_argument(
        "--max-pages", type=int, default=100, help="page ceiling per specialty (erdv)"
    )
    parser.add_argument("--only", default=None, help="one specialty slug, for testing")
    args = parser.parse_args()

    specialties = [args.only] if args.only else list(SPECIALTIES)
    stats = Stats()
    listings: list[Listing] = []

    for specialty in specialties:
        found: list[Listing] = []
        if args.source in ("telecontact", "both"):
            for ville in TC_VILLES:
                found += scrape_telecontact(specialty, ville)
        if args.source in ("erdv", "both"):
            found += scrape_erdv(specialty, args.city, args.max_pages, stats)
        listings += found
        stats.by_specialty[specialty] = len(found)
        print(f"  {specialty:16} {len(found):5} listings")

    rows = dedupe(listings)
    print(f"\n{len(listings)} listings -> {len(rows)} after dedupe")

    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    "full_name": item.full_name,
                    "specialty": item.specialty,
                    "city": item.city,
                    "district": item.district,
                    "address": item.address,
                    "source_name": item.source_name,
                    "source": item.source,
                    "source_id": item.source_id,
                    "source_url": item.source_url,
                }
            )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
