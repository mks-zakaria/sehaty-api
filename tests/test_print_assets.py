"""Tests for the plaque / QR-card generator.

The failure mode this guards against is specific and expensive: a QR that looks
plausible but decodes to nothing, discovered only after plaques are already on
waiting-room walls. `draw_qr` reconstructs the code by hand from segno's matrix,
so a transposition, mirror or off-by-one would produce exactly that. The central
test replays the drawing operations back into a matrix and compares it to
segno's, which catches all three without needing a camera.

Skipped when the `print` extra is not installed:
    uv run --extra print pytest tests/test_print_assets.py
"""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("reportlab", reason="install the 'print' extra")
pytest.importorskip("segno", reason="install the 'print' extra")

import segno  # noqa: E402
from reportlab.lib.pagesizes import A4, A5  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "print_assets.py"
_spec = importlib.util.spec_from_file_location("print_assets", _SCRIPT)
print_assets = importlib.util.module_from_spec(_spec)
sys.modules["print_assets"] = print_assets
_spec.loader.exec_module(print_assets)

DoctorCard = print_assets.DoctorCard


class RecordingCanvas:
    """Captures the rectangles `draw_qr` emits instead of drawing them."""

    def __init__(self) -> None:
        self.rects: list[tuple[float, float, float, float]] = []

    def setFillColor(self, *_args, **_kwargs) -> None:  # noqa: N802 - reportlab API
        pass

    def rect(self, x, y, w, h, stroke=0, fill=1) -> None:  # noqa: ANN001
        self.rects.append((x, y, w, h))


def _replay_to_matrix(url: str, size: float = 100.0) -> list[list[int]]:
    """Draw ``url``, then rebuild the module grid from the emitted rectangles."""
    recorder = RecordingCanvas()
    print_assets.draw_qr(recorder, url, 0.0, 0.0, size)

    qr = segno.make(url, error="m")
    n = len(list(qr.matrix))
    quiet = 4
    unit = size / (n + quiet * 2)

    grid = [[0] * n for _ in range(n)]
    for x, y, w, h in recorder.rects:
        col = round(x / unit) - quiet
        row = n - 1 - (round(y / unit) - quiet)
        span = round(w / unit)
        assert abs(h - unit) < 1e-6, "each rect should be exactly one module tall"
        for offset in range(span):
            grid[row][col + offset] = 1
    return grid


class TestQrGeometry:
    def test_reproduces_segnos_matrix_exactly(self) -> None:
        # Catches transposition, mirroring and off-by-one — the three ways a
        # hand-drawn QR silently stops decoding.
        url = "https://sehaty.ma/dr/dr-amina-bennani-casablanca?src=qr"
        expected = [[1 if bit else 0 for bit in row] for row in segno.make(url, error="m").matrix]
        assert _replay_to_matrix(url) == expected

    def test_finder_pattern_lands_top_left(self) -> None:
        # Orientation check independent of the matrix comparison: the top-left
        # finder is a solid 7x7 block in every valid QR.
        grid = _replay_to_matrix("https://sehaty.ma/dr/x")
        assert all(grid[0][c] == 1 for c in range(7))
        assert all(grid[r][0] == 1 for r in range(7))
        assert grid[1][1] == 0  # the ring's white gap

    def test_emits_horizontal_runs_not_one_rect_per_module(self) -> None:
        # Same image, a fraction of the PDF operators.
        recorder = RecordingCanvas()
        print_assets.draw_qr(recorder, "https://sehaty.ma/dr/x", 0.0, 0.0, 100.0)
        modules_drawn = sum(1 for _ in segno.make("https://sehaty.ma/dr/x", error="m").matrix)
        assert len(recorder.rects) < modules_drawn * modules_drawn

    def test_leaves_a_quiet_zone(self) -> None:
        # Scanners fail without the spec's 4-module margin.
        recorder = RecordingCanvas()
        size = 100.0
        print_assets.draw_qr(recorder, "https://sehaty.ma/dr/x", 0.0, 0.0, size)
        n = len(list(segno.make("https://sehaty.ma/dr/x", error="m").matrix))
        unit = size / (n + 8)
        assert min(x for x, _, _, _ in recorder.rects) >= 4 * unit - 1e-6
        assert max(x + w for x, _, w, _ in recorder.rects) <= size - 4 * unit + 1e-6

    def test_stays_inside_the_requested_box(self) -> None:
        recorder = RecordingCanvas()
        print_assets.draw_qr(recorder, "https://sehaty.ma/dr/x", 10.0, 20.0, 50.0)
        assert all(10.0 <= x and x + w <= 60.0 + 1e-6 for x, _, w, _ in recorder.rects)
        assert all(20.0 <= y and y + h <= 70.0 + 1e-6 for _, y, _, h in recorder.rects)


class TestUrl:
    def test_carries_the_qr_attribution_marker(self) -> None:
        # Without ?src=qr a scan is indistinguishable from web traffic, and the
        # plaque's whole value ("34 scans last month") becomes unprovable.
        card = DoctorCard(slug="dr-x", full_name="Dr X", specialty=None, city=None)
        assert card.url.endswith("/dr/dr-x?src=qr")


class TestSpecialtyLabel:
    @pytest.mark.parametrize(
        ("slug", "expected"),
        [
            # Printing the raw slug would put "dentistry" on a Moroccan wall.
            ("dentistry", "Dentiste"),
            ("generalist", "Médecin généraliste"),
            ("otolaryngology", "ORL"),
            ("sports-medicine", "Sports Medicine"),  # unknown: title-cased
            (None, None),
            ("", None),
        ],
    )
    def test_renders_a_french_label(self, slug: str | None, expected: str | None) -> None:
        assert print_assets.specialty_label(slug) == expected


class TestDocuments:
    def _doctors(self) -> list[DoctorCard]:
        return [
            DoctorCard("dr-a", "Dr. Amina Bennani", "Dentiste", "Casablanca"),
            DoctorCard("dr-b", "Dr. Youssef Tazi", "Cardiologue", "Casablanca"),
        ]

    def test_plaques_are_one_page_per_doctor(self, tmp_path: Path) -> None:
        out = tmp_path / "plaques.pdf"
        pdf = canvas.Canvas(str(out), pagesize=A5)
        for doctor in self._doctors():
            print_assets.draw_plaque(pdf, doctor)
        pdf.save()

        data = out.read_bytes()
        assert data.startswith(b"%PDF")
        assert data.count(b"/Type /Page") - data.count(b"/Type /Pages") == 2

    def test_cards_fill_ten_per_sheet(self, tmp_path: Path) -> None:
        out = tmp_path / "cards.pdf"
        pdf = canvas.Canvas(str(out), pagesize=A4)
        print_assets.draw_card_sheets(pdf, self._doctors()[0], copies=25)
        pdf.save()

        data = out.read_bytes()
        pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
        assert pages == 3  # 10 + 10 + 5

    def test_a_long_name_is_shrunk_rather_than_overflowing(self, tmp_path: Path) -> None:
        # Long Moroccan names are common; silently running off the edge of a
        # printed plaque is not recoverable once it is on a wall.
        pdf = canvas.Canvas(str(tmp_path / "x.pdf"), pagesize=A5)
        long_name = "Dr. Abdelmajid Benkirane-Tazi El Fassi Alaoui"
        width = A5[0] - 28 * print_assets.mm
        size = print_assets._fit_font(pdf, long_name, "Helvetica-Bold", 22, width)
        assert size < 22
        assert pdf.stringWidth(long_name, "Helvetica-Bold", size) <= width


class TestCsvLoading:
    def test_reads_the_shipped_sample(self) -> None:
        sample = _SCRIPT.parent / "doctors.sample.csv"
        doctors = print_assets.load_from_csv(sample)

        assert len(doctors) == 8
        first = doctors[0]
        assert first.slug == "dr-amina-bennani-casablanca"
        # French, not the CSV's slug.
        assert first.specialty == "Dentiste"
        assert first.url.endswith("?src=qr")

    def test_slugs_match_the_importers(self) -> None:
        # A plaque printed before the import must point at the page the import
        # will create — otherwise every early plaque is a 404.
        sys.path.insert(0, str(_SCRIPT.parent))
        import_spec = importlib.util.spec_from_file_location(
            "import_doctors_check", _SCRIPT.parent / "import_doctors.py"
        )
        module = importlib.util.module_from_spec(import_spec)
        sys.modules["import_doctors_check"] = module
        import_spec.loader.exec_module(module)

        for doctor in print_assets.load_from_csv(_SCRIPT.parent / "doctors.sample.csv"):
            assert doctor.slug == module.doctor_slug(doctor.full_name, doctor.city)
