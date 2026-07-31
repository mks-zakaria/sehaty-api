#!/usr/bin/env python3
"""Turn a medical textbook PDF into retrievable chunks.

The first half of the article pipeline: `build_corpus.py` reads a book once and
writes JSONL that `draft_articles.py` retrieves from. Splitting it in two is
deliberate — extraction is slow, deterministic and worth caching, while drafting
is none of those things and gets re-run whenever a prompt changes.

**The corpus is never committed.** Unlike the doctor snapshots next door, these
are in-copyright textbooks; the repository carries the code that reads them and
not a copy of their contents. Whoever runs this supplies their own book. That is
also why every chunk keeps `work` and `page`: an article's citation has to point
at a real passage a doctor can open and check, and a fact whose source cannot be
named has no business on a page about someone's illness.

Two page shapes are handled, because the two books differ:

* **single column** (Pathology Illustrated) — born-digital text, extracted whole;
* **two column** (Sinelnikov's atlas) — a scan whose columns interleave line by
  line when read naively, producing sentences that alternate between two
  unrelated topics. Cropping each column separately is the difference between a
  usable chunk and confident nonsense.

Usage:

    python scripts/build_corpus.py \\
        --pdf ~/Desktop/"Pathology Illustrated-683hlm.pdf" \\
        --work "Pathology Illustrated (7th ed.), Reid et al." \\
        --short pathology

    python scripts/build_corpus.py \\
        --pdf ~/Desktop/"Sinelnikov Vol I(1).pdf" \\
        --work "Sinelnikov, Atlas of Human Anatomy, Vol. I" \\
        --short anatomy --columns 2
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Chunk sizing. Long enough to carry a whole idea — a paragraph on the aetiology
# of a disease is useless cut in half — and short enough that a handful fit in a
# prompt beside the instructions.
TARGET_CHARS = 1600
MAX_CHARS = 2600
# Below this a chunk is a page number, a figure caption or a running header, and
# retrieving it only crowds out something that says something.
MIN_CHARS = 200

# A heading in both books: short, mostly capitals, no sentence punctuation.
_HEADING = re.compile(r"^[A-Z][A-Z \-'’&,()/]{3,60}$")


def page_count(pdf: Path) -> int:
    out = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True
    ).stdout
    match = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if not match:
        raise SystemExit(f"cannot read page count from {pdf}")
    return int(match.group(1))


def page_width(pdf: Path, page: int) -> float:
    out = subprocess.run(
        ["pdfinfo", "-f", str(page), "-l", str(page), str(pdf)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    match = re.search(r"size:\s+([\d.]+) x ([\d.]+)", out)
    return float(match.group(1)) if match else 612.0


def _extract(pdf: Path, page: int, crop: tuple[float, float, float] | None = None) -> str:
    cmd = ["pdftotext", "-f", str(page), "-l", str(page)]
    if crop:
        x, w, h = crop
        cmd += ["-x", str(int(x)), "-y", "0", "-W", str(int(w)), "-H", str(int(h))]
    cmd += [str(pdf), "-"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""


def read_page(
    pdf: Path, page: int, *, columns: int, width: float | None = None
) -> tuple[str, str | None]:
    """One page's body text, plus the heading it sits under if it has one.

    Headings are read from the *uncropped* page even in two-column mode: they
    span the full width, so a crop cuts them in half and "THE VERTEBRAE" becomes
    "THE VER" — a heading no retrieval will ever match.
    """
    full = _extract(pdf, page)
    # The longest candidate, not the first. The first is the running header —
    # "IMMUNITY" on every page of the chapter — which groups sixty pages into one
    # topic and makes retrieval useless. The section title under it
    # ("CELLULAR BASIS OF THE ADAPTIVE IMMUNE RESPONSE") is both longer and the
    # thing a chunk is actually about.
    candidates = [
        line.strip()
        for line in full.splitlines()
        if _HEADING.fullmatch(line.strip())
    ]
    heading = max(candidates, key=len).title() if candidates else None

    if columns < 2:
        return full, heading

    # Passed in by the caller: every page of a book is the same size, and asking
    # pdfinfo per page spawns four hundred processes to learn one number.
    width = width if width is not None else page_width(pdf, page)
    gutter = width / 2
    # A hair of overlap either side of the gutter: a crop exactly on it clips the
    # last glyph of every line in the left column.
    left = _extract(pdf, page, (0, gutter - 5, 2000))
    right = _extract(pdf, page, (gutter + 5, width - gutter, 2000))
    return f"{left}\n{right}", heading


# Lines that are page furniture rather than content: running headers, and the
# distribution watermarks that redistributed scans carry on every page. Left in,
# they appear in most chunks and score against every query.
_BOILERPLATE = re.compile(
    r"facebook\.com|t\.me/|blogspot|^\s*\|.*\|\s*$"
    # Typesetting furniture: "ORL_10.fm Page 90 Lundi, 13. décembre 2010".
    r"|\.fm\s+Page\s+\d+",
    re.I,
)


def clean(text: str) -> str:
    """Whitespace and hyphenation only.

    Nothing here tries to repair the scan's OCR errors ("arc" for "are",
    "tkoracica" for "thoracica"). A regex that edits medical terms it does not
    understand will eventually turn one drug or one artery into another, and a
    silent corruption in a corpus is far worse than a visible typo — the typo
    survives into the draft where a doctor sees it, the corruption does not.
    """
    text = "\n".join(
        line for line in text.splitlines() if not _BOILERPLATE.search(line)
    )
    text = text.replace("\xad", "")
    # Words broken across a line end: "an­\nteriorly" -> "anteriorly".
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_pages(pages: list[tuple[int, str, str | None]], work: str, short: str) -> list[dict]:
    """Group pages into chunks that stay under one heading.

    Chunks break on a heading change first and on size second, so a chunk is
    always about one thing. The page range travels with it: a citation of "pages
    107-108" is checkable, a citation of "Pathology Illustrated" is not.
    """
    chunks: list[dict] = []
    buffer: list[str] = []
    first_page = last_page = 0
    heading: str | None = None

    def flush() -> None:
        nonlocal buffer, first_page, last_page
        body = clean("\n\n".join(buffer))
        if len(body) >= MIN_CHARS:
            chunks.append(
                {
                    "work": work,
                    "short": short,
                    "heading": heading,
                    "page_from": first_page,
                    "page_to": last_page,
                    "text": body,
                }
            )
        buffer = []

    for page_no, text, page_heading in pages:
        body = clean(text)
        if not body:
            continue
        starts_new = page_heading is not None and page_heading != heading
        too_big = sum(len(b) for b in buffer) + len(body) > MAX_CHARS
        if buffer and (starts_new or too_big):
            flush()
        if not buffer:
            first_page = page_no
            heading = page_heading or heading
        last_page = page_no
        buffer.append(body)
        if sum(len(b) for b in buffer) >= TARGET_CHARS:
            flush()

    if buffer:
        flush()
    return chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--work", required=True, help="Citation as it will be printed")
    parser.add_argument("--short", required=True, help="Corpus key, e.g. pathology")
    parser.add_argument("--columns", type=int, default=1, choices=(1, 2))
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--pages", default=None, help="Range like 20-120, for a trial run")
    args = parser.parse_args()

    pdf = args.pdf.expanduser()
    if not pdf.exists():
        raise SystemExit(f"no such file: {pdf}")

    total = page_count(pdf)
    first, last = 1, total
    if args.pages:
        first, _, last_raw = args.pages.partition("-")
        first, last = int(first), int(last_raw or first)
    last = min(last, total)

    print(f"reading {pdf.name}: pages {first}-{last} of {total}", file=sys.stderr)
    width = page_width(pdf, first) if args.columns > 1 else None
    pages = []
    for page_no in range(first, last + 1):
        text, heading = read_page(pdf, page_no, columns=args.columns, width=width)
        pages.append((page_no, text, heading))
        if page_no % 50 == 0:
            print(f"  … page {page_no}", file=sys.stderr)

    chunks = chunk_pages(pages, args.work, args.short)

    out = args.out or Path(__file__).parent / "data" / "corpus" / f"{args.short}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    chars = sum(len(c["text"]) for c in chunks)
    print(
        f"wrote {len(chunks)} chunks ({chars:,} chars) to {out}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
