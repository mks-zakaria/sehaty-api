#!/usr/bin/env python3
"""Draft patient-facing articles from the textbook corpora.

The second half of the pipeline. `build_corpus.py` turned two books into
retrievable chunks; this retrieves the passages for a topic, asks the model to
write from *those passages only*, checks what comes back, and writes drafts an
admin can post.

Three gates, each guarding a different failure:

**Coverage.** A topic with no supporting passages is skipped and reported, never
written from the model's own memory. The whole point of citing a textbook is
that a doctor can check the claim; an article about someone's illness whose
source cannot be named fails the one test this feature exists to pass.

**Verbatim overlap.** A draft sharing a long run of words with its sources is
rejected. Facts are not copyrightable, expression is — and these are
in-copyright books. This turns "we paraphrase, honestly" into a check that
actually runs. It also catches the model quoting a textbook register at patients
who came for an answer, not a lecture.

**Language.** Each topic is written in French and in Arabic *from the same
passages*, rather than one being a translation of the other. A mistranslated
clinical term is the error a validating doctor is least likely to catch, because
it reads fluently.

Nothing here publishes. Every draft lands as DRAFT with no author, for a doctor
to validate and an admin to review — the two steps that turn machine text into
something with a name on it.

Usage:

    # See what would be written, without calling a model or the API:
    python scripts/draft_articles.py --dry-run

    # Draft, and write them to a file to read:
    python scripts/draft_articles.py --out drafts.jsonl

    # Draft and create them through the API:
    python scripts/draft_articles.py --post http://localhost:8000 --token "$ADMIN_TOKEN"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DATA = Path(__file__).parent / "data"
CORPUS_DIR = DATA / "corpus"
TOPICS = DATA / "article_topics.json"

# How many passages go into a prompt. Enough to write 400 words from, few enough
# that the model cannot pad the article with whatever it finds least relevant.
CONTEXT_CHUNKS = 4
# A topic needs this many passages before it is worth writing at all.
MIN_CHUNKS = 2
# And the best of them has to be this relevant — two weak hits on the word "skin"
# is not coverage of eczema.
MIN_SCORE = 3.0

# The longest run of identical words a draft may share with a source. Twelve is
# past the point where a shared run is a coincidence of medical vocabulary and
# into reproducing someone's sentence.
MAX_VERBATIM_RUN = 12

LOCALES = ("fr", "ar")


def fold(text: str) -> str:
    """Lowercase and strip accents, so one term matches both languages.

    The corpus is now half English (pathology, anatomy) and half French
    (dermatology, psychiatry). Without folding, "alopecie" never matches
    "alopécie" and a French source silently supports nothing.
    """
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


@dataclass
class Chunk:
    work: str
    short: str
    heading: str | None
    page_from: int
    page_to: int
    text: str
    # Folded once, here rather than in the loader: a Chunk built any other way
    # would score against nothing at all, silently.
    folded: str = field(default="", repr=False)
    folded_heading: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self.folded = fold(self.text)
        self.folded_heading = fold(self.heading or "")

    @property
    def locator(self) -> str:
        pages = (
            f"p. {self.page_from}"
            if self.page_from == self.page_to
            else f"pp. {self.page_from}-{self.page_to}"
        )
        return f"{self.heading}, {pages}" if self.heading else pages


def load_corpus(directory: Path = CORPUS_DIR) -> list[Chunk]:
    """Every chunk from every corpus file.

    A missing directory is a clear error rather than an empty list: silently
    drafting from nothing would produce articles that cite nothing, which is the
    exact outcome the citation requirement exists to prevent.
    """
    files = sorted(directory.glob("*.jsonl")) if directory.exists() else []
    if not files:
        raise SystemExit(
            f"no corpus in {directory} — run scripts/build_corpus.py first "
            "(the books are not in this repository; supply your own copy)"
        )
    chunks = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                chunks.append(Chunk(**json.loads(line)))
    return chunks


_WORD = re.compile(r"[a-zà-ÿ]+")


def _words(text: str) -> list[str]:
    return _WORD.findall(text.lower())


@lru_cache(maxsize=512)
def _pattern(term: str) -> re.Pattern[str]:
    """Word-bounded matcher for one folded term.

    Substring matching quietly inflated everything short: "gale" (scabies) hit
    286 occurrences of "également", making it look like the best-sourced skin
    condition we had. Counting words rather than character runs is the fix, and
    it matters most for exactly the short French terms this corpus is full of.
    """
    return re.compile(rf"\b{re.escape(term)}\b")


def _alternatives(terms: list[str]) -> list[str]:
    """Flatten the `a|b` synonym syntax used to name one thing in two languages."""
    return [part for term in terms for part in term.split("|") if part.strip()]


def score(chunk: Chunk, terms: list[str]) -> float:
    """How well one passage answers one topic.

    Deliberately plain term matching rather than embeddings: it needs no model,
    no key and no index, it is inspectable when a topic is skipped, and the terms
    are already curated per topic. A heading match counts double — a passage
    *titled* "Osteoarthritis" is about osteoarthritis, while one that mentions it
    once may be about something else entirely.
    """
    body = chunk.folded
    heading = chunk.folded_heading
    total = 0.0
    for term in _alternatives(terms):
        pattern = _pattern(fold(term))
        hits = len(pattern.findall(body))
        if hits:
            # Diminishing returns: forty mentions is not twenty times better than
            # two, it is usually a chapter that happens to repeat a word.
            total += min(hits, 5)
        if pattern.search(heading):
            total += 5
    return total


def is_source(chunk: Chunk) -> bool:
    """Whether a chunk is prose worth citing.

    The book's own index and contents pages are term-dense by construction, so
    they outrank real passages for almost any query — "Index, p. 667" was being
    retrieved as a source on anaemia. They are navigation, not medicine.
    """
    heading = chunk.folded_heading.strip()
    if heading in {
        "index",
        "contents",
        "references",
        "bibliography",
        "glossary",
        "sommaire",
        "table des matieres",
        "bibliographie",
    }:
        return False
    # A page that is mostly page numbers is an index whatever its heading says.
    digits = sum(ch.isdigit() for ch in chunk.text)
    return digits / max(len(chunk.text), 1) < 0.12


def retrieve(chunks: list[Chunk], terms: list[str], limit: int = CONTEXT_CHUNKS) -> list[Chunk]:
    scored = [(score(c, terms), c) for c in chunks if is_source(c)]
    scored = [(s, c) for s, c in scored if s > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:limit]]


def sense_check(chunks: list[Chunk], term: str, limit: int = 2) -> list[str]:
    """A few real sentences containing the term, for a human to eyeball.

    Term counting cannot tell word senses apart, and one homonym is enough to
    produce a confidently sourced article about the wrong thing: "depression"
    passed this gate on passages that say "depressed scar", "depression of
    function" and "diaphragm depressed" — none of which is the mood disorder.

    So the gate stays a filter and never an authority. Printing the term in
    context turns a silent false pass into an obvious one, before anybody writes
    four hundred words on top of it.
    """
    found: list[str] = []
    needle = term.lower()
    for chunk in chunks:
        for sentence in re.split(r"(?<=[.])\s+", chunk.text):
            if needle in sentence.lower():
                found.append(" ".join(sentence.split())[:120])
                break
        if len(found) >= limit:
            break
    return found


def covered(chunks: list[Chunk], terms: list[str]) -> tuple[bool, str]:
    """Whether the corpus can actually support this topic, and why not if it cannot.

    The first term is the condition itself and it is *required*; the rest are
    supporting vocabulary. Without that rule the gate passes on generic words —
    "eczema" scored a comfortable pass on three passages that say "skin" and
    nothing about eczema, which is precisely the article this check exists to
    refuse to write.
    """
    # The first entry names the condition, and may list synonyms with `|` so one
    # topic can be satisfied by an English or a French source.
    primaries = [fold(p) for p in terms[0].split("|") if p.strip()]
    named = [
        c
        for c in chunks
        if is_source(c)
        and any(
            _pattern(p).search(c.folded) or _pattern(p).search(c.folded_heading) for p in primaries
        )
    ]
    if len(named) < MIN_CHUNKS:
        return False, f"only {len(named)} passage(s) name '{terms[0]}'"

    best = max(score(c, terms) for c in named)
    if best < MIN_SCORE:
        return False, f"best passage naming it scores {best:.1f}, below {MIN_SCORE}"
    return True, ""


def longest_shared_run(draft: str, sources: list[str]) -> int:
    """The longest run of consecutive words the draft shares with any source.

    Word-level rather than character-level because that is the unit copyright
    cares about and the unit a reader recognises: eight identical words in a row
    is a borrowed sentence however the punctuation was changed.
    """
    draft_words = _words(draft)
    longest = 0
    for source in sources:
        source_text = " ".join(_words(source))
        # Walk every window in the draft, longest first is unnecessary — a simple
        # extend-while-matching scan is linear enough for a few thousand words.
        start = 0
        while start < len(draft_words):
            run = 0
            while start + run < len(draft_words):
                candidate = " ".join(draft_words[start : start + run + 1])
                if candidate in source_text:
                    run += 1
                else:
                    break
            longest = max(longest, run)
            start += max(run, 1)
    return longest


PROMPT = """You are writing for Sehaty, a Moroccan health directory read by patients,
not by doctors.

Write ONE article answering this question: {question}

Language: write entirely in {language}. Do not translate an existing article —
write it fresh in this language.

Use ONLY the medical facts in the passages below. If the passages do not cover
something, leave it out. Do not invent statistics, drug doses, prices, or
anything specific to Morocco that is not in the passages.

WHO IS READING: someone worried about themselves or a relative, with no medical
training, on a phone, who typed this question into Google. They want an answer in
the first sentence, not an introduction.

STRUCTURE — follow exactly:
1. Open with a direct answer to the question in 40-60 words. No preamble, no
   "dans cet article nous allons voir". Someone who reads only this paragraph
   must leave with the answer.
2. Then 4 to 6 short sections. Each section starts with a "## " subheading that
   is itself a question a reader would ask next, and holds 2-4 short paragraphs.
   Never more than 4 sentences in a paragraph.
3. A section headed "## Quand consulter un médecin" listing the specific signs
   that mean see someone, and which mean go now.
4. End with "## Questions fréquentes" and 2 to 4 question/answer pairs, each
   answer 1-3 sentences.

Use markdown: "## " for subheadings, blank line between paragraphs, "- " for the
few lists. No tables, no images, no links, no bold-everything.

STYLE — readability is the product, not a finishing touch. Someone is reading
this on a phone, worried, in their second or third language:
- 350 to 500 words total. Over 550 and it stops being read.
- one idea per sentence, and no sentence over 25 words
- no more than 3 sentences per paragraph
- prefer the short word: "abîme" over "endommage", "il n'y a pas" over
  "il n'existe aucun"
- explain each medical term the first time you use it
- plain, calm, factual. No reassurance you cannot support, no alarm
- NEVER tell the reader what they have or what treatment to take. Describe what
  the condition is, how it is generally recognised, and when to see a doctor
- no promotional language of any kind, and never name or praise a clinic
- rewrite everything in your own words; do not copy phrases from the passages

ILLUSTRATIONS: propose 2 images that would genuinely help this reader understand
— an anatomical diagram, a comparison, a chart of what a test measures. Describe
what each should show, factually enough that someone could source or draw it.
Do not propose stock photographs of smiling people.

THE SUMMARY IS THE SHARE TEXT. It becomes the preview line when the article is
pasted into WhatsApp, which is how these actually travel here. So it is not an
abstract of the article — it is the single claim that makes someone send it on.

The claims that travel contradict something the reader already believes, and name
something they have felt but had no word for:
  weak: "Cet article explique les causes de la gastrite chronique."
  strong: "Ce n'est pas le stress. Dans 80 % des gastrites chroniques, c'est une bactérie."
  strong: "Une douleur de poitrine qui cède au repos est une alerte.
           Une douleur qui ne cède pas est une urgence."

It must be a claim the article itself makes and sources. A share line the body
cannot support is the fastest way to lose the trust the citation was for.
Max 200 characters.

Return ONLY valid JSON, no markdown fence:
{{"title": "...",
  "summary": "the ONE sentence someone would forward to their family — see below",
  "body": "the article in markdown",
  "images": [{{"brief": "what this illustration should show",
              "alt": "alt text for a screen reader"}}]}}

PASSAGES:
{context}
"""

LANGUAGE_NAMES = {"fr": "French", "ar": "Modern Standard Arabic", "ary": "Moroccan Darija"}


def build_prompt(question: str, locale: str, passages: list[Chunk]) -> str:
    context = "\n\n---\n\n".join(f"[{c.work} — {c.locator}]\n{c.text}" for c in passages)
    return PROMPT.format(question=question, language=LANGUAGE_NAMES[locale], context=context)


def parse_draft(raw: str) -> dict:
    """Pull the JSON object out of whatever the model returned.

    Models wrap JSON in prose or a markdown fence often enough that failing on it
    would mean losing a whole batch to formatting.
    """
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in the model's reply")
    return json.loads(text[start : end + 1])


def post_article(base: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{base.rstrip('/')}/api/v1/admin/articles",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Retrieve and report, call nothing")
    parser.add_argument("--out", type=Path, default=None, help="Write drafts to this JSONL")
    parser.add_argument("--post", default=None, help="API base URL to create drafts through")
    parser.add_argument("--token", default=None, help="Admin bearer token, with --post")
    parser.add_argument("--specialty", default=None, help="Only this specialty")
    parser.add_argument("--limit", type=int, default=None, help="At most N topics")
    args = parser.parse_args()

    chunks = load_corpus()
    plan = json.loads(TOPICS.read_text(encoding="utf-8"))["topics"]
    if args.specialty:
        plan = [t for t in plan if t["specialty"] == args.specialty]
    if args.limit:
        plan = plan[: args.limit]

    print(f"corpus: {len(chunks)} passages | topics: {len(plan)}\n", file=sys.stderr)

    drafts, skipped = [], []
    for topic in plan:
        ok, why = covered(chunks, topic["terms"])
        passages = retrieve(chunks, topic["terms"])
        label = f"{topic['specialty']:<15} {topic['question'][:52]}"
        if not ok:
            skipped.append((topic, why))
            print(f"  ✗ {label}  — {why}", file=sys.stderr)
            continue

        best = score(passages[0], topic["terms"])
        print(f"  ✓ {label}  ({len(passages)} passages, best {best:.0f})", file=sys.stderr)
        if args.dry_run:
            for passage in passages:
                print(f"      · {passage.work} — {passage.locator}", file=sys.stderr)
            # The term in context — read these before trusting the tick above.
            for quote in sense_check(passages, topic["terms"][0]):
                print(f"        “{quote}”", file=sys.stderr)
            continue

        from sehaty.core.services import llm  # imported late: --dry-run needs no key

        for locale in LOCALES:
            try:
                raw = llm.complete(build_prompt(topic["question"], locale, passages))
                draft = parse_draft(raw)
            except Exception as error:  # noqa: BLE001 - one topic must not end the run
                print(f"      ! {locale}: {error}", file=sys.stderr)
                continue

            shared = longest_shared_run(draft["body"], [p.text for p in passages])
            if shared > MAX_VERBATIM_RUN:
                print(
                    f"      ! {locale}: {shared} words copied verbatim — rejected",
                    file=sys.stderr,
                )
                continue

            drafts.append(
                {
                    "title": draft["title"],
                    "summary": draft.get("summary"),
                    "body": draft["body"],
                    "locale": locale,
                    "specialty_slug": topic["specialty"],
                    "sources": [{"work": p.work, "locator": p.locator} for p in passages],
                    # Briefs, not images. The model can say what an illustration
                    # should show; it cannot produce one, and a fabricated medical
                    # diagram is worse than none. Sourcing happens after.
                    "image_briefs": draft.get("images", []),
                }
            )
            print(f"      + {locale}: {len(draft['body'])} chars", file=sys.stderr)

    print(
        f"\ndrafted {len(drafts)} | skipped {len(skipped)} topics for lack of sources",
        file=sys.stderr,
    )
    if skipped:
        print("add a source book covering:", file=sys.stderr)
        for topic, why in skipped:
            print(f"  {topic['specialty']:<15} {topic['question']}  ({why})", file=sys.stderr)

    if args.out:
        args.out.write_text(
            "\n".join(json.dumps(d, ensure_ascii=False) for d in drafts) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.out}", file=sys.stderr)

    if args.post:
        if not args.token:
            raise SystemExit("--post needs --token")
        for draft in drafts:
            try:
                created = post_article(args.post, args.token, draft)
                print(f"created #{created['id']} {created['slug']}", file=sys.stderr)
            except urllib.error.HTTPError as error:
                print(f"! {draft['title'][:40]}: {error.read().decode()[:160]}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
