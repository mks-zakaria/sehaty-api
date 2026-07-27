#!/usr/bin/env python
"""Generate the printed half of the Pack Présence: waiting-room plaques + QR cards.

Two deliverables, both print-ready PDFs:

  * **Plaque** — A5 portrait, one per doctor, for the waiting-room wall. Doctor
    name, specialty, a large QR, and the instruction to scan it.
  * **Cards**  — A4 sheets of 85x55mm pocket cards (10 per sheet) with crop
    marks, for the reception desk.

The QR is drawn as **vector rectangles**, not as an embedded bitmap. A raster QR
looks fine on screen and prints with soft edges that cheap phone cameras
struggle to decode from across a waiting room — which would make the single
physical object the doctor paid for the thing that does not work.

Every QR carries `?src=qr` so scans are attributable in the landing analytics.
That is what turns "your plaque is on the wall" into "your plaque produced 34
scans last month" three months later.

Usage:
    cd sehaty-api
    # every published doctor, straight from the database
    uv run --extra print python scripts/print_assets.py --out ./print

    # or without a database, from the same CSV the importer takes
    uv run --extra print python scripts/print_assets.py \
        --csv scripts/doctors.sample.csv --out ./print

    # one doctor
    uv run --extra print python scripts/print_assets.py \
        --slug dr-amina-bennani-casablanca --out ./print

Note: the printed text is French only. reportlab does not shape Arabic, and
rendering it unshaped would print disconnected, reversed letters — worse than
omitting it. Adding Arabic needs a bundled Arabic-capable TTF plus
arabic-reshaper/python-bidi; the landing page it points to is already trilingual.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import segno
from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

# Brand palette, matching the landing site.
BRAND = HexColor("#2b73b3")
BRAND_DARK = HexColor("#1b3d5e")
BRAND_MINT = HexColor("#2fae9b")
INK = HexColor("#0f172a")
MUTED = HexColor("#64748b")
HAIRLINE = Color(0.85, 0.87, 0.90)

SITE_URL = os.environ.get("SEHATY_SITE_URL", "https://sehaty.ma").rstrip("/")

# Card geometry: standard Moroccan business-card size, 2 columns x 5 rows on A4.
CARD_W, CARD_H = 85 * mm, 55 * mm
CARD_COLS, CARD_ROWS = 2, 5


# French display names for the seeded specialty catalogue. CSV mode has no
# database to resolve a slug against, and printing the raw slug would put
# "dentistry" on a Moroccan doctor's waiting-room wall. Database mode reads
# `Specialty.name_fr` directly and never consults this.
_SPECIALTY_FR = {
    "generalist": "Médecin généraliste",
    "cardiology": "Cardiologue",
    "dermatology": "Dermatologue",
    "pediatrics": "Pédiatre",
    "dentistry": "Dentiste",
    "gynecology": "Gynécologue",
    "ophthalmology": "Ophtalmologue",
    "otolaryngology": "ORL",
    "psychiatry": "Psychiatre",
    "orthopedics": "Orthopédiste",
}


def specialty_label(slug: str | None) -> str | None:
    """French name for a specialty slug; unknown slugs are title-cased."""
    if not slug:
        return None
    return _SPECIALTY_FR.get(slug.strip().lower(), slug.strip().replace("-", " ").title())


@dataclass
class DoctorCard:
    """The only fields a printed asset needs."""

    slug: str
    full_name: str
    specialty: str | None
    city: str | None

    @property
    def url(self) -> str:
        # `src=qr` makes the scan attributable in the landing analytics.
        return f"{SITE_URL}/dr/{self.slug}?src=qr"


def draw_qr(pdf: canvas.Canvas, url: str, x: float, y: float, size: float) -> None:
    """Draw ``url`` as a vector QR whose bottom-left corner is at (x, y).

    Vector rather than an embedded image: crisp at any print resolution, which
    is what makes it scannable from across a room.
    """
    qr = segno.make(url, error="m")
    matrix = list(qr.matrix)
    # A 4-module quiet zone is required by the spec; scanners fail without it.
    quiet = 4
    modules = len(matrix) + quiet * 2
    unit = size / modules

    pdf.setFillColor(INK)
    for row_index, row in enumerate(matrix):
        col_start = None
        for col_index in range(len(row) + 1):
            filled = col_index < len(row) and row[col_index]
            if filled and col_start is None:
                col_start = col_index
            elif not filled and col_start is not None:
                # Emit each horizontal run as one rectangle rather than one per
                # module: same image, a fraction of the PDF operators.
                run = col_index - col_start
                pdf.rect(
                    x + (col_start + quiet) * unit,
                    y + size - (row_index + quiet + 1) * unit,
                    run * unit,
                    unit,
                    stroke=0,
                    fill=1,
                )
                col_start = None


def _wordmark(pdf: canvas.Canvas, x: float, y: float, size: float) -> None:
    """The Sehaty mark: a rounded square with a cross, plus the wordmark."""
    pdf.setFillColor(BRAND)
    pdf.roundRect(x, y, size, size, size * 0.28, stroke=0, fill=1)
    pdf.setFillColor(Color(1, 1, 1))
    bar = size * 0.14
    pdf.rect(x + size / 2 - bar / 2, y + size * 0.24, bar, size * 0.52, stroke=0, fill=1)
    pdf.rect(x + size * 0.24, y + size / 2 - bar / 2, size * 0.52, bar, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", size * 0.9)
    pdf.drawString(x + size * 1.4, y + size * 0.22, "Sehaty")


def _fit_font(pdf: canvas.Canvas, text: str, font: str, start: float, max_w: float) -> float:
    """Largest size <= ``start`` at which ``text`` fits ``max_w``.

    Long Moroccan names ("Dr. Abdelmajid Benkirane-Tazi") are common; shrinking
    beats silently overflowing off the edge of a printed plaque.
    """
    size = start
    while size > 6 and pdf.stringWidth(text, font, size) > max_w:
        size -= 0.5
    return size


def draw_plaque(pdf: canvas.Canvas, doctor: DoctorCard) -> None:
    """One A5 waiting-room plaque."""
    width, height = A5
    margin = 14 * mm
    inner = width - 2 * margin

    pdf.setFillColor(Color(1, 1, 1))
    pdf.rect(0, 0, width, height, stroke=0, fill=1)

    # Brand band across the top.
    pdf.setFillColor(BRAND)
    pdf.rect(0, height - 8 * mm, width, 8 * mm, stroke=0, fill=1)

    _wordmark(pdf, margin, height - 22 * mm, 7 * mm)

    # Doctor identity.
    name_size = _fit_font(pdf, doctor.full_name, "Helvetica-Bold", 22, inner)
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", name_size)
    pdf.drawCentredString(width / 2, height - 42 * mm, doctor.full_name)

    if doctor.specialty:
        pdf.setFillColor(MUTED)
        size = _fit_font(pdf, doctor.specialty, "Helvetica", 13, inner)
        pdf.setFont("Helvetica", size)
        pdf.drawCentredString(width / 2, height - 50 * mm, doctor.specialty)

    # The QR itself — the reason the plaque exists.
    qr_size = 72 * mm
    draw_qr(pdf, doctor.url, (width - qr_size) / 2, height - 132 * mm, qr_size)

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawCentredString(width / 2, height - 148 * mm, "Prenez rendez-vous en ligne")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(
        width / 2, height - 156 * mm, "Scannez ce code avec l'appareil photo de votre téléphone"
    )

    # Readable fallback for anyone whose camera will not scan.
    pdf.setFillColor(BRAND)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawCentredString(width / 2, height - 168 * mm, f"{SITE_URL}/dr/{doctor.slug}")

    pdf.setStrokeColor(BRAND_MINT)
    pdf.setLineWidth(1.2)
    pdf.line(margin, 18 * mm, width - margin, 18 * mm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, 12 * mm, "sehaty.ma — votre santé, simplement")

    pdf.showPage()


def _draw_card(pdf: canvas.Canvas, doctor: DoctorCard, x: float, y: float) -> None:
    """One pocket card at the given bottom-left corner."""
    pdf.setStrokeColor(HAIRLINE)
    pdf.setLineWidth(0.3)
    pdf.roundRect(x, y, CARD_W, CARD_H, 3 * mm, stroke=1, fill=0)

    qr_size = 34 * mm
    draw_qr(pdf, doctor.url, x + 6 * mm, y + (CARD_H - qr_size) / 2, qr_size)

    text_x = x + 46 * mm
    text_w = CARD_W - 52 * mm

    pdf.setFillColor(BRAND_DARK)
    size = _fit_font(pdf, doctor.full_name, "Helvetica-Bold", 10.5, text_w)
    pdf.setFont("Helvetica-Bold", size)
    pdf.drawString(text_x, y + CARD_H - 16 * mm, doctor.full_name)

    if doctor.specialty:
        pdf.setFillColor(MUTED)
        size = _fit_font(pdf, doctor.specialty, "Helvetica", 8.5, text_w)
        pdf.setFont("Helvetica", size)
        pdf.drawString(text_x, y + CARD_H - 21 * mm, doctor.specialty)

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 8.5)
    pdf.drawString(text_x, y + 19 * mm, "Rendez-vous en ligne")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(text_x, y + 14 * mm, "Scannez ce code")
    pdf.setFillColor(BRAND)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(text_x, y + 8 * mm, "sehaty.ma")


def _crop_marks(pdf: canvas.Canvas, x: float, y: float) -> None:
    """Short guides at the card corners so a shop can trim accurately."""
    pdf.setStrokeColor(HAIRLINE)
    pdf.setLineWidth(0.25)
    reach = 3 * mm
    for cx, cy in ((x, y), (x + CARD_W, y), (x, y + CARD_H), (x + CARD_W, y + CARD_H)):
        pdf.line(cx - reach, cy, cx + reach, cy)
        pdf.line(cx, cy - reach, cx, cy + reach)


def draw_card_sheets(pdf: canvas.Canvas, doctor: DoctorCard, copies: int) -> None:
    """A4 sheets of identical pocket cards, 10 per sheet."""
    width, height = A4
    per_sheet = CARD_COLS * CARD_ROWS
    margin_x = (width - CARD_COLS * CARD_W) / 2
    margin_y = (height - CARD_ROWS * CARD_H) / 2

    remaining = copies
    while remaining > 0:
        on_this_sheet = min(per_sheet, remaining)
        for index in range(on_this_sheet):
            col, row = index % CARD_COLS, index // CARD_COLS
            x = margin_x + col * CARD_W
            y = height - margin_y - (row + 1) * CARD_H
            _crop_marks(pdf, x, y)
            _draw_card(pdf, doctor, x, y)
        remaining -= on_this_sheet
        pdf.showPage()


def load_from_csv(path: Path) -> list[DoctorCard]:
    """Read doctors from the same CSV the importer takes."""
    # Imported here to avoid a hard dependency when running from the database.
    sys.path.insert(0, str(Path(__file__).parent))
    from import_doctors import doctor_slug  # noqa: PLC0415

    doctors: list[DoctorCard] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            name = (row.get("full_name") or "").strip()
            if not name:
                continue
            city = (row.get("city") or "").strip() or None
            doctors.append(
                DoctorCard(
                    slug=doctor_slug(name, city),
                    full_name=name,
                    specialty=specialty_label(row.get("specialty")),
                    city=city,
                )
            )
    return doctors


def load_from_db(slug: str | None) -> list[DoctorCard]:
    """Read published doctors (optionally one) straight from the database."""
    from sehaty.db import DoctorProfile, DoctorSpecialty, Specialty, User, VerificationStatus
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set (or pass --csv)")

    engine = create_engine(url, future=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    stmt = (
        select(
            DoctorProfile.slug,
            DoctorProfile.full_name,
            DoctorProfile.city,
            Specialty.name_fr,
        )
        .join(User, User.id == DoctorProfile.user_id)
        .outerjoin(DoctorSpecialty, DoctorSpecialty.doctor_id == DoctorProfile.user_id)
        .outerjoin(Specialty, Specialty.id == DoctorSpecialty.specialty_id)
        .where(
            User.is_active.is_(True),
            DoctorProfile.verification_status == VerificationStatus.VERIFIED,
        )
        .order_by(DoctorProfile.slug.asc())
    )
    if slug:
        stmt = stmt.where(DoctorProfile.slug == slug)

    with factory() as session:
        rows = session.execute(stmt).all()

    # A doctor with several specialties yields several rows; keep the first.
    seen: dict[str, DoctorCard] = {}
    for row in rows:
        if row.slug not in seen:
            seen[row.slug] = DoctorCard(
                slug=row.slug,
                full_name=row.full_name,
                specialty=row.name_fr,
                city=row.city,
            )
    return list(seen.values())


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate plaques and QR cards.")
    parser.add_argument("--out", type=Path, default=Path("print"), help="Output directory")
    parser.add_argument("--csv", type=Path, help="Read doctors from a CSV instead of the DB")
    parser.add_argument("--slug", help="Only this doctor (database mode)")
    parser.add_argument(
        "--cards", type=int, default=100, help="Pocket cards per doctor (default 100)"
    )
    args = parser.parse_args()

    if args.csv and not args.csv.is_file():
        print(f"no such file: {args.csv}", file=sys.stderr)
        return 2

    doctors = load_from_csv(args.csv) if args.csv else load_from_db(args.slug)
    if not doctors:
        print("no doctors to print", file=sys.stderr)
        return 1

    args.out.mkdir(parents=True, exist_ok=True)

    plaques_path = args.out / "plaques.pdf"
    plaques = canvas.Canvas(str(plaques_path), pagesize=A5)
    plaques.setTitle("Sehaty — plaques salle d'attente")
    for doctor in doctors:
        draw_plaque(plaques, doctor)
    plaques.save()

    for doctor in doctors:
        cards_path = args.out / f"cards-{doctor.slug}.pdf"
        cards = canvas.Canvas(str(cards_path), pagesize=A4)
        cards.setTitle(f"Sehaty — cartes {doctor.full_name}")
        draw_card_sheets(cards, doctor, args.cards)
        cards.save()

    print(f"{len(doctors)} doctor(s)")
    print(f"  plaques : {plaques_path}")
    print(f"  cards   : {args.out}/cards-<slug>.pdf ({args.cards} per doctor)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
