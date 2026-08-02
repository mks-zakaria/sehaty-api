#!/usr/bin/env python
"""Find freely-licensed illustrations for articles that have image briefs.

Every article is written with briefs — "a diagram of the ear canal, labels in
French" — and no pictures. The brief is a note to whoever sources the image,
because a writer can say what a diagram should show and must not invent the
diagram itself. A fabricated medical illustration is worse than none: a reader
trusts a picture of an artery far more readily than a sentence about one, and
cannot check it.

So this searches Wikimedia Commons and *proposes* candidates. It never attaches
anything. Matching a picture to a brief is a judgement no search engine can
make, and the first run demonstrated it precisely: the top hit for the thyroid
article was `File:Thyroid nodules.svg` — exact filename, open licence, ample
resolution, and on opening it, a radiologist's classification tree of
echogenicity and elastography. Correct subject, useless to a patient, and an
automatic pipeline would have published it.

Same rule as the text, for the same reason: nothing goes on the page unless a
person has looked at it.

The workflow is two steps, with a human in the middle:

    python scripts/suggest_images.py --batch batch-2026-08-summer.jsonl \\
        --out review.json     # search, and write candidates out
    # open review.json, look at each image, keep the good ones
    python scripts/apply_images.py --file review.json --direct

Only licences that permit commercial reuse with attribution are kept. Public
domain and CC0 need no credit but get one anyway; CC BY and CC BY-SA are
carried with the author and licence recorded, because an uncredited CC BY image
is simply an infringing one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

DATA = Path(__file__).parent / "data" / "articles"

# Commons asks for a descriptive agent with contact details.
USER_AGENT = "Sehaty/1.0 (patient health articles; contact@sehaty.ma)"

# Licences that allow commercial reuse. Anything else is skipped rather than
# reported: an image we cannot legally publish is not a candidate, and listing
# it only invites someone to use it later without re-checking.
ALLOWED = (
    "public domain",
    "cc0",
    "cc by 2.0",
    "cc by 3.0",
    "cc by 4.0",
    "cc by-sa 2.0",
    "cc by-sa 3.0",
    "cc by-sa 4.0",
)

# Below this an image is a thumbnail: unusable full-width on a page, and much
# worse in a video frame.
MIN_WIDTH = 500

# Commons holds enormous numbers of digitised books, and a French-language
# search matches their titles far more readily than it matches a diagram: the
# first pass of this script returned nothing but scanned 19th-century medical
# treatises. These are documents, not illustrations.
DOCUMENT_SUFFIXES = (".djvu", ".pdf", ".tif", ".tiff", ".webm", ".ogv")


def _clean(html: str | None) -> str:
    """Strip the markup Commons returns in its metadata fields."""
    if not html:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def search_commons(query: str, limit: int = 6) -> list[dict]:
    url = (
        "https://commons.wikimedia.org/w/api.php?action=query&format=json"
        f"&generator=search&gsrnamespace=6&gsrlimit={limit}"
        f"&gsrsearch={urllib.parse.quote(query)}"
        "&prop=imageinfo&iiprop=url|extmetadata|size&iiurlwidth=1400"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except Exception as error:  # noqa: BLE001 - a failed search is not fatal
        print(f"    ! search failed: {error}", file=sys.stderr)
        return []

    out = []
    for page in payload.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        licence = _clean(meta.get("LicenseShortName", {}).get("value"))
        width = info.get("width") or 0
        title = page.get("title", "")
        if licence.lower() not in ALLOWED or width < MIN_WIDTH:
            continue
        if title.lower().endswith(DOCUMENT_SUFFIXES):
            continue
        out.append(
            {
                "title": title,
                "url": info.get("thumburl") or info.get("url", ""),
                "descriptionurl": info.get("descriptionurl", ""),
                "width": width,
                "height": info.get("height") or 0,
                "license": licence,
                "credit": _clean(meta.get("Artist", {}).get("value")) or "Wikimedia Commons",
            }
        )
    return out


# What to search for, per topic. Commons is indexed in English and titled by
# subject, so a French brief searched literally returns French *books* — the
# first version of this script found nothing but scanned treatises. The topic
# key is already an English handle for the subject, so it does most of the work;
# these add the anatomical vocabulary a diagram is actually filed under.
TOPIC_QUERIES = {
    "otitis-externa-swimming": ["ear anatomy diagram", "outer ear canal anatomy"],
    "diabetes-beach-feet": ["diabetic foot", "foot anatomy diagram", "capillary diagram"],
    "summer-food-poisoning": ["salmonella", "typhoid fever", "bacteria illustration"],
    "atopic-eczema-summer": ["atopic dermatitis", "eczema skin"],
    "sunburn-degrees": ["sunburn", "burn degrees diagram", "skin layers anatomy"],
    "varicose-veins-heavy-legs": ["varicose veins", "vein valve diagram"],
    "thyroid-nodule": ["thyroid gland anatomy", "thyroid nodule", "goitre"],
    "panic-attack": ["anxiety", "human nervous system diagram"],
    "depression-recognising": ["depression mental health", "brain anatomy diagram"],
    "antidepressants-timeline": ["antidepressant", "serotonin synapse diagram"],
    "telogen-effluvium": ["hair follicle anatomy", "hair growth cycle diagram"],
    "traction-alopecia": ["traction alopecia", "hair follicle anatomy"],
    "hypertension-silent-killer": ["artery wall diagram", "hypertension"],
    "type-2-diabetes-signs": ["insulin diagram", "pancreas anatomy"],
    "anaemia-fatigue": ["red blood cells", "anemia blood smear"],
    "kidney-stones": ["kidney stone", "kidney anatomy diagram"],
    "heart-attack-warning-signs": ["heart anatomy diagram", "coronary artery"],
    "h-pylori-heartburn": ["helicobacter pylori", "stomach anatomy diagram"],
    "vitamin-d-deficiency": ["vitamin D", "bone anatomy"],
    "heart-failure-breathless-swelling": ["heart failure", "heart anatomy diagram"],
    "overweight-when-a-risk": ["obesity", "body mass index chart"],
}


def queries_for(
    brief: str, alt: str, title: str, topic_key: str | None, index: int = 0
) -> list[str]:
    """Searches Commons can actually answer, for one brief.

    `index` rotates the topic's query list so the second brief in an article
    starts from the second subject. An article asks for two *different*
    pictures — a diagram and a photograph, an anatomy and a mechanism — and
    without this both briefs came back with the same six candidates.

    Falls back to the topic key itself when the topic is not in the table above,
    so a new batch still returns something rather than nothing — but a hand-
    written English query is what makes the difference between a diagram and a
    scanned book.
    """
    if topic_key and topic_key in TOPIC_QUERIES:
        queries = TOPIC_QUERIES[topic_key]
        # Rotate rather than slice: every query stays reachable, so a brief
        # whose own subject finds nothing still falls back to the others.
        start = index % len(queries)
        return queries[start:] + queries[:start]
    if topic_key:
        return [topic_key.replace("-", " ")]
    return [re.sub(r"[^\w\s'-]", " ", title).strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, help="Batch file under scripts/data/articles/")
    parser.add_argument("--out", type=Path, required=True, help="Where to write the review file")
    parser.add_argument(
        "--locale",
        default="fr",
        help="Only search from this locale's articles — the two languages share "
        "a topic, so searching both would ask the same question twice.",
    )
    parser.add_argument("--per-brief", type=int, default=6)
    args = parser.parse_args()

    path = DATA / args.batch
    if not path.exists():
        print(f"no such batch: {path}", file=sys.stderr)
        return 1

    review = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        article = json.loads(line)
        if article.get("locale") != args.locale:
            continue
        print(f"\n{article['title'][:70]}", file=sys.stderr)
        for index, image in enumerate(article.get("images", [])):
            if image.get("url"):
                continue
            brief = image.get("brief", "")
            print(f"  brief {index + 1}: {brief[:64]}", file=sys.stderr)
            candidates: list[dict] = []
            seen = set()
            for query in queries_for(
                brief, image.get("alt", ""), article["title"], article.get("topic_key"), index
            ):
                for hit in search_commons(query, args.per_brief):
                    if hit["url"] in seen:
                        continue
                    seen.add(hit["url"])
                    hit["found_by"] = query
                    candidates.append(hit)
                time.sleep(0.3)
                if len(candidates) >= args.per_brief:
                    break
            for candidate in candidates[: args.per_brief]:
                print(
                    f"      {candidate['license']:16} {candidate['width']}px  "
                    f"{candidate['title'][5:60]}",
                    file=sys.stderr,
                )
            review.append(
                {
                    "topic_key": article.get("topic_key"),
                    "article_title": article["title"],
                    "image_index": index,
                    "brief": brief,
                    "alt": image.get("alt"),
                    # Nothing is chosen here. Set "chosen" to one of the
                    # candidates' urls after looking at it, or leave it null to
                    # publish the article with no picture — which stays the
                    # right answer when nothing on Commons actually shows what
                    # the brief describes.
                    "chosen": None,
                    "candidates": candidates[: args.per_brief],
                }
            )

    args.out.write_text(json.dumps(review, ensure_ascii=False, indent=1), encoding="utf-8")
    briefs = len(review)
    found = sum(1 for entry in review if entry["candidates"])
    print(
        f"\n{briefs} briefs, {found} with candidates, 0 chosen — open {args.out} and pick",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
