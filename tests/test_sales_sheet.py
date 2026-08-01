"""Tests for the Pack Présence sales one-pager.

Mostly a consistency guard. The sheet is handed to a doctor and read while you
talk, so a figure that drifts from the commercial model contradicts you in
print — which costs more than having no sheet at all. These pin the numbers and
the promises that must appear.

Skipped when the `print` extra is not installed:
    uv run --extra print pytest tests/test_sales_sheet.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("reportlab", reason="install the 'print' extra")

from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sales_sheet.py"
_spec = importlib.util.spec_from_file_location("sales_sheet", _SCRIPT)
sales_sheet = importlib.util.module_from_spec(_spec)
sys.modules["sales_sheet"] = sales_sheet
_spec.loader.exec_module(sales_sheet)


def _all_text() -> str:
    """Every string the sheet renders, flattened for substring assertions."""
    parts = [title + " " + detail for title, detail in sales_sheet.DELIVERABLES]
    parts += sales_sheet.NOT_INCLUDED
    parts += [q + " " + a for q, a in sales_sheet.OBJECTIONS]
    return "\n".join(parts)


class TestOffer:
    def test_lists_exactly_the_seven_deliverables(self) -> None:
        assert len(sales_sheet.DELIVERABLES) == 7

    def test_every_deliverable_has_a_concrete_detail(self) -> None:
        # A bare title reads as a promise; the detail is what makes it checkable.
        for title, detail in sales_sheet.DELIVERABLES:
            assert title.strip()
            assert len(detail.strip()) > 25, title

    @pytest.mark.parametrize(
        "promise",
        [
            "plaque QR",
            "100 cartes",
            "fiche Google",
            "photos",
            "statistiques",
        ],
    )
    def test_names_each_tangible_item(self, promise: str) -> None:
        assert promise in _all_text()


class TestNotIncluded:
    def test_is_stated_in_print(self) -> None:
        # Selling twenty doctors on an implied feature creates twenty
        # obligations; saying it here is what makes the rest credible.
        assert len(sales_sheet.NOT_INCLUDED) >= 4

    def test_says_booking_is_not_live_yet(self) -> None:
        assert "Pas de réservation en ligne" in "\n".join(sales_sheet.NOT_INCLUDED)

    def test_refuses_to_promise_patients(self) -> None:
        joined = "\n".join(sales_sheet.NOT_INCLUDED)
        assert "Aucune garantie de nouveaux patients" in joined


class TestObjections:
    def test_covers_the_objections_that_actually_come_up(self) -> None:
        questions = " ".join(q for q, _ in sales_sheet.OBJECTIONS)
        for fragment in ("assez de patients", "Dabadoc", "cher", "réfléchir"):
            assert fragment in questions, fragment

    def test_every_objection_has_an_answer(self) -> None:
        for question, answer in sales_sheet.OBJECTIONS:
            assert answer.strip(), question
            assert len(answer) > 40, question


class TestPricingConsistency:
    """The figures must match the agreed commercial model, not drift from it."""

    @pytest.mark.parametrize(
        "figure",
        [
            "600 DH TTC",  # one-time pack
            "900 DH",  # struck-through list price
            "199 DH TTC",  # founding monthly rate
            "349 DH",  # public monthly price
            "597 DH TTC",  # quarterly
            "1 990 DH TTC",  # annual, two months free
        ],
    )
    def test_renders_each_price(self, figure: str, tmp_path: Path) -> None:
        pdf = canvas.Canvas(str(tmp_path / "s.pdf"), pagesize=A4)
        drawn: list[str] = []
        original = pdf.drawString

        def capture(x, y, text, *a, **kw):  # noqa: ANN001
            drawn.append(text)
            return original(x, y, text, *a, **kw)

        pdf.drawString = capture  # type: ignore[method-assign]
        sales_sheet.draw_recto(pdf)
        assert any(figure in line for line in drawn), f"{figure} missing from the recto"

    def test_the_trial_clock_starts_at_activation(self, tmp_path: Path) -> None:
        # The single most important sentence on the page: selling "3 months
        # free" from the payment date would burn the trial building the feature.
        pdf = canvas.Canvas(str(tmp_path / "s.pdf"), pagesize=A4)
        drawn: list[str] = []
        original = pdf.drawString
        pdf.drawString = lambda x, y, t, *a, **k: (  # type: ignore[method-assign]
            drawn.append(t),
            original(x, y, t, *a, **k),
        )[1]
        sales_sheet.draw_recto(pdf)
        joined = " ".join(drawn)
        assert "agenda est activé" in joined
        assert "pas le jour du paiement" in joined

    def test_states_prices_are_tax_inclusive(self, tmp_path: Path) -> None:
        # Doctors cannot recover TVA, so a figure that grows 20% on the invoice
        # is a trust problem on the very first transaction.
        pdf = canvas.Canvas(str(tmp_path / "s.pdf"), pagesize=A4)
        drawn: list[str] = []
        original = pdf.drawString
        pdf.drawString = lambda x, y, t, *a, **k: (  # type: ignore[method-assign]
            drawn.append(t),
            original(x, y, t, *a, **k),
        )[1]
        sales_sheet.draw_recto(pdf)
        joined = " ".join(drawn)
        assert "TTC" in joined
        assert "TVA 20 %" in joined

    def test_never_bills_monthly(self) -> None:
        # Collecting cash from twenty cabinets every month does not scale.
        pdf = canvas.Canvas(str(Path("/dev/null")), pagesize=A4)
        drawn: list[str] = []
        original = pdf.drawString
        pdf.drawString = lambda x, y, t, *a, **k: (  # type: ignore[method-assign]
            drawn.append(t),
            original(x, y, t, *a, **k),
        )[1]
        sales_sheet.draw_recto(pdf)
        joined = " ".join(drawn)
        assert "trimestre" in joined and "année" in joined


class TestIssuingCompany:
    def test_names_the_billing_entity(self, tmp_path: Path) -> None:
        pdf = canvas.Canvas(str(tmp_path / "s.pdf"), pagesize=A4)
        drawn: list[str] = []
        original = pdf.drawCentredString
        pdf.drawCentredString = lambda x, y, t, *a, **k: (  # type: ignore[method-assign]
            drawn.append(t),
            original(x, y, t, *a, **k),
        )[1]
        sales_sheet.draw_recto(pdf)
        assert any(sales_sheet.COMPANY["name"] in line for line in drawn)

    def test_registration_numbers_are_blanks_not_invented(self) -> None:
        # A fabricated RC or ICE reads as a real registration on a document the
        # doctor keeps; an obvious blank is far safer than plausible digits.
        for key in ("rc", "ice", "if"):
            value = sales_sheet.COMPANY[key]
            assert not any(ch.isdigit() for ch in value), f"{key} looks fabricated"


class TestDocument:
    def test_is_a_two_page_pdf(self, tmp_path: Path) -> None:
        out = tmp_path / "pack.pdf"
        pdf = canvas.Canvas(str(out), pagesize=A4)
        sales_sheet.draw_recto(pdf)
        sales_sheet.draw_verso(pdf)
        pdf.save()

        data = out.read_bytes()
        assert data.startswith(b"%PDF")
        assert data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2


class TestWrapping:
    def test_wraps_within_the_measured_width(self, tmp_path: Path) -> None:
        pdf = canvas.Canvas(str(tmp_path / "w.pdf"), pagesize=A4)
        text = " ".join(["cabinet"] * 60)
        lines = sales_sheet.wrap(pdf, text, "Helvetica", 9.5, 200)
        assert len(lines) > 1
        for line in lines:
            assert pdf.stringWidth(line, "Helvetica", 9.5) <= 200

    def test_keeps_a_word_longer_than_the_column(self, tmp_path: Path) -> None:
        # Dropping it silently would lose content off the page.
        pdf = canvas.Canvas(str(tmp_path / "w.pdf"), pagesize=A4)
        lines = sales_sheet.wrap(pdf, "anticonstitutionnellement", "Helvetica", 9.5, 20)
        assert lines == ["anticonstitutionnellement"]
