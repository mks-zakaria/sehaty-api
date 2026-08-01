"""Tests for the payment receipts.

Two things are worth testing on a document generator, and they are both about
what the paper claims.

The **amount in words** is the point of the exercise: on a Moroccan receipt it
is what makes the figure hard to alter afterwards, and French spells numbers
with enough exceptions — quatre-vingts, deux cents, mille, million — that a
naive speller writes something subtly wrong on every hundredth receipt. So the
speller is tested against the awkward cases, and against the totals actually
printed.

The **figures** are pinned to the commercial model. A receipt that disagrees
with the sales sheet is worse than no receipt: it is a contradiction in the
doctor's own file.

Skipped when the `print` extra is not installed:
    uv run --extra print pytest tests/test_receipts.py
"""

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("reportlab", reason="install the 'print' extra")

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
_spec = importlib.util.spec_from_file_location("receipts", _SCRIPTS / "receipts.py")
receipts = importlib.util.module_from_spec(_spec)
sys.modules["receipts"] = receipts
_spec.loader.exec_module(receipts)

ISSUED = date(2026, 8, 1)


class TestAmountInWords:
    @pytest.mark.parametrize(
        ("amount", "expected"),
        [
            (1, "un dirham"),
            (2, "deux dirhams"),
            (17, "dix-sept dirhams"),
            (21, "vingt et un dirhams"),
            # The seventies and nineties are built on sixty and eighty.
            (71, "soixante et onze dirhams"),
            (77, "soixante-dix-sept dirhams"),
            (91, "quatre-vingt-onze dirhams"),
            # quatre-vingts keeps its s only when nothing follows.
            (80, "quatre-vingts dirhams"),
            (81, "quatre-vingt-un dirhams"),
            (80_000, "quatre-vingt mille dirhams"),
            # Same rule for cent.
            (200, "deux cents dirhams"),
            (201, "deux cent un dirhams"),
            (200_000, "deux cent mille dirhams"),
            (100, "cent dirhams"),
            # mille is invariable and never takes "un".
            (1_000, "mille dirhams"),
            (2_000, "deux mille dirhams"),
            # million is a noun: it pluralises, and a round one takes "de".
            (1_000_000, "un million de dirhams"),
            (2_000_000, "deux millions de dirhams"),
            (1_500_000, "un million cinq cent mille dirhams"),
        ],
    )
    def test_spells_the_awkward_cases(self, amount: int, expected: str) -> None:
        assert receipts.in_words(amount) == expected

    def test_spells_the_centimes_apart(self) -> None:
        assert receipts.in_words(1234.56) == (
            "mille deux cent trente-quatre dirhams et cinquante-six centimes"
        )
        assert receipts.in_words(2.01) == "deux dirhams et un centime"

    def test_rounds_to_the_centime_before_spelling(self) -> None:
        """The words and the figure must agree exactly.

        A float summing to 596.9999 prints as 597,00 — spelling out five hundred
        and ninety-six would put two different amounts on the same paper.
        """
        assert receipts.in_words(596.999) == receipts.in_words(597)

    def test_refuses_a_negative_amount(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            receipts.in_words(-1)


class TestFormatting:
    def test_groups_thousands_the_french_way(self) -> None:
        assert receipts.money(2988) == "2 988,00"
        assert receipts.money(600) == "600,00"
        assert receipts.money(1234.5) == "1 234,50"


class TestTheThreeReceipts:
    def setup_method(self) -> None:
        self.presence, self.presence_rdv, self.renewal = receipts.examples(ISSUED, 1, 2026)

    def test_the_presence_pack_is_six_hundred_dirhams_once(self) -> None:
        assert self.presence.total == 600.0
        assert len(self.presence.items) == 1
        assert self.presence.items[0].quantity == 1
        assert "unique" in self.presence.period

    def test_presence_plus_rdv_is_the_pack_plus_twelve_months(self) -> None:
        """600 + 12 × 199 — inside the 1 200-3 500 first-year band."""
        assert self.presence_rdv.total == 600.0 + 12 * 199.0
        assert self.presence_rdv.total == 2988.0
        assert 1200 <= self.presence_rdv.total <= 3500

    def test_the_renewal_is_a_quarter_of_the_founding_rate(self) -> None:
        assert self.renewal.total == 3 * 199.0
        assert "Virement" in self.renewal.method

    def test_the_words_match_the_figures(self) -> None:
        assert receipts.in_words(self.presence.total) == "six cents dirhams"
        assert receipts.in_words(self.presence_rdv.total) == (
            "deux mille neuf cent quatre-vingt-huit dirhams"
        )
        assert receipts.in_words(self.renewal.total) == ("cinq cent quatre-vingt-dix-sept dirhams")

    def test_receipt_numbers_are_sequential_within_the_year(self) -> None:
        numbers = [r.number for r in receipts.examples(ISSUED, 7, 2026)]
        assert numbers == ["SEH-2026-0007", "SEH-2026-0008", "SEH-2026-0009"]

    def test_every_example_is_marked_specimen(self) -> None:
        """A sample must never be passable as a real receipt."""
        assert all(r.specimen for r in receipts.examples(ISSUED, 1, 2026))

    def test_the_free_page_is_not_sold_twice(self) -> None:
        """The page is free forever; only the agenda is a subscription."""
        assert "gratuite" in " ".join(self.renewal.notes)


class TestRendering:
    def test_writes_one_pdf_per_receipt(self, tmp_path: Path) -> None:
        sys.argv = ["receipts.py", "--out", str(tmp_path), "--date", "2026-08-01"]
        assert receipts.main() == 0

        written = sorted(p.name for p in tmp_path.glob("*.pdf"))
        assert written == [
            "recu-presence-rdv.pdf",
            "recu-presence.pdf",
            "recu-rdv-renouvellement.pdf",
        ]
        for pdf in tmp_path.glob("*.pdf"):
            assert pdf.stat().st_size > 1000, pdf

    def test_each_page_carries_both_copies(self, tmp_path: Path) -> None:
        """Client copy and souche on one sheet, so the numbers cannot drift."""
        pytest.importorskip("pypdf")
        from pypdf import PdfReader

        sys.argv = ["receipts.py", "--out", str(tmp_path)]
        receipts.main()

        text = PdfReader(tmp_path / "recu-presence.pdf").pages[0].extract_text()
        assert "EXEMPLAIRE CLIENT" in text.upper()
        assert "SOUCHE" in text.upper()
        assert text.upper().count("REÇU DE PAIEMENT") == 2

    def test_the_issuing_company_is_named_on_the_paper(self, tmp_path: Path) -> None:
        """A commercial document a doctor keeps has to say who billed them."""
        pytest.importorskip("pypdf")
        from pypdf import PdfReader

        sys.argv = ["receipts.py", "--out", str(tmp_path)]
        receipts.main()

        text = PdfReader(tmp_path / "recu-presence.pdf").pages[0].extract_text()
        assert receipts.COMPANY["name"] in text
        assert "ICE" in text
