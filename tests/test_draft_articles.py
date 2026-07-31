"""The gates between a textbook and a published health article.

Three properties, and each one is the difference between a page worth having and
a liability:

* a topic the books do not cover is refused, not written from the model's memory;
* a draft that reproduces a textbook's sentences is rejected, because facts are
  free and expression is not;
* the book's own index never becomes a citation.

The script lives in `scripts/`, outside the importable package, so it is loaded
by path — the same way `import_doctors` is.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "draft_articles.py"
_spec = importlib.util.spec_from_file_location("draft_articles", _SCRIPT)
draft_articles = importlib.util.module_from_spec(_spec)
sys.modules["draft_articles"] = draft_articles
_spec.loader.exec_module(draft_articles)

Chunk = draft_articles.Chunk


def _chunk(text: str, heading: str | None = None, page: int = 10) -> Chunk:
    return Chunk(
        work="Pathology Illustrated (7th ed.)",
        short="pathology",
        heading=heading,
        page_from=page,
        page_to=page,
        text=text,
    )


class TestCoverage:
    def test_a_topic_the_books_cover_is_written(self) -> None:
        chunks = [
            _chunk(
                "Osteoarthritis is a degenerative disease of articular cartilage. " * 4,
                heading="Osteoarthritis",
            ),
            _chunk("In osteoarthritis the joint space narrows and osteophytes form. " * 4),
        ]

        ok, why = draft_articles.covered(chunks, ["osteoarthritis", "cartilage", "joint"])

        assert ok is True, why

    def test_generic_words_are_not_coverage(self) -> None:
        """The failure this gate exists for.

        Three passages that say "skin" and nothing about eczema scored a
        comfortable pass before the condition itself was made a requirement —
        which would have published an article on eczema sourced from passages
        that never mention it.
        """
        chunks = [
            _chunk("The skin consists of epidermis and dermis. " * 5),
            _chunk("Skin biopsy is used in the diagnosis of many conditions. " * 5),
            _chunk("The epidermis renews itself continuously. " * 5),
        ]

        ok, why = draft_articles.covered(chunks, ["eczema", "skin", "epidermis"])

        assert ok is False
        assert "eczema" in why

    def test_one_passing_mention_is_not_enough(self) -> None:
        chunks = [
            _chunk("Otitis media is inflammation of the middle ear. " * 4, heading="The Ear"),
            _chunk("The middle ear contains three ossicles. " * 5),
        ]

        ok, why = draft_articles.covered(chunks, ["otitis", "middle ear", "tympanic"])

        assert ok is False
        assert "1 passage" in why

    def test_the_reason_is_reported_not_swallowed(self) -> None:
        """A skipped topic has to become a shopping list for the next book."""
        ok, why = draft_articles.covered([_chunk("nothing relevant here " * 20)], ["migraine"])

        assert ok is False
        assert why


class TestSourceSelection:
    @pytest.mark.parametrize("heading", ["Index", "Contents", "References", "GLOSSARY"])
    def test_the_books_own_navigation_is_never_a_source(self, heading: str) -> None:
        """ "Index, p. 667" was being cited as the source on anaemia.

        An index is term-dense by construction, so it outranks real prose for
        almost any query while containing no medicine at all.
        """
        index = _chunk("anaemia 396 aneurysm 212", heading=heading)
        assert draft_articles.is_source(index) is False

    def test_a_page_of_page_numbers_is_an_index_whatever_it_is_called(self) -> None:
        numbers = " ".join(f"term {n}" for n in range(200, 320))
        assert draft_articles.is_source(_chunk(numbers, heading="Something Else")) is False

    def test_ordinary_prose_is_a_source(self) -> None:
        prose = "Atheroma begins as a fatty streak in the intima of a large artery. " * 4
        assert draft_articles.is_source(_chunk(prose, heading="Atheroma")) is True

    def test_a_heading_match_outranks_a_passing_mention(self) -> None:
        titled = _chunk("This describes the condition in detail. " * 5, heading="Osteoporosis")
        mentions = _chunk("Osteoporosis is mentioned here once among other things. " * 2)

        assert draft_articles.score(titled, ["osteoporosis"]) > draft_articles.score(
            mentions, ["osteoporosis"]
        )


class TestVerbatimOverlap:
    SOURCE = (
        "Atheroma begins as a fatty streak in the intima of a large artery, "
        "progressing to a fibrolipid plaque which may ulcerate and thrombose."
    )

    def test_a_copied_sentence_is_caught(self) -> None:
        draft = (
            "Voici ce qui arrive. Atheroma begins as a fatty streak in the intima of a "
            "large artery, progressing to a fibrolipid plaque. Voilà."
        )

        assert draft_articles.longest_shared_run(draft, [self.SOURCE]) > (
            draft_articles.MAX_VERBATIM_RUN
        )

    def test_shared_medical_vocabulary_is_not_copying(self) -> None:
        """The check must not fire on the words the subject requires.

        An article about atheroma that cannot say "fibrolipid plaque" is not an
        article; the threshold sits above ordinary term reuse and below a
        borrowed sentence.
        """
        draft = (
            "L'athérome commence par une accumulation de graisse dans la paroi de "
            "l'artère. Avec le temps une plaque se forme et peut se rompre."
        )

        assert draft_articles.longest_shared_run(draft, [self.SOURCE]) <= (
            draft_articles.MAX_VERBATIM_RUN
        )

    def test_an_empty_draft_shares_nothing(self) -> None:
        assert draft_articles.longest_shared_run("", [self.SOURCE]) == 0


class TestModelReply:
    def test_json_survives_a_markdown_fence(self) -> None:
        """Models wrap JSON in a fence often enough that failing on it would lose
        a whole batch to formatting."""
        reply = '```json\n{"title": "T", "summary": "S", "body": "B"}\n```'

        assert draft_articles.parse_draft(reply)["title"] == "T"

    def test_json_survives_surrounding_chatter(self) -> None:
        reply = 'Bien sûr ! Voici :\n{"title": "T", "summary": "S", "body": "B"}\nJ\'espère que...'

        assert draft_articles.parse_draft(reply)["body"] == "B"

    def test_a_reply_with_no_json_is_an_error_not_a_silent_skip(self) -> None:
        with pytest.raises(ValueError):
            draft_articles.parse_draft("I cannot help with that.")


class TestCitations:
    def test_a_citation_points_at_a_page_a_doctor_can_open(self) -> None:
        single = _chunk("text", heading="Atheroma", page=205)
        assert single.locator == "Atheroma, p. 205"

        spread = Chunk(
            work="w", short="s", heading="Heart Failure", page_from=199, page_to=201, text="t"
        )
        assert spread.locator == "Heart Failure, pp. 199-201"
