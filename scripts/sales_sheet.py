#!/usr/bin/env python
"""Generate the Pack Présence sales one-pager (A4, recto/verso, French).

The sheet you hand across a doctor's desk. Recto is the offer; verso is what is
explicitly *not* included plus the objections you will actually hear, with an
answer for each.

The "not included" block is on the sheet deliberately. Selling twenty doctors on
an implied feature creates twenty obligations, and the fastest way to lose a
600 DH customer is to have promised booking that does not exist yet. Saying it
in print is what makes the rest of the page credible.

Prices here must stay in step with the commercial model: 600 DH one-time (list
900), then 199 DH/month founding rate locked 24 months against a 349 public
price, billed quarterly or annually — never monthly, because collecting cash
from twenty cabinets every month does not scale.

**Every figure is TTC.** Doctors cannot recover TVA — medical acts are largely
exempt in Morocco — so a price that grows 20% on the invoice is a trust problem
on the very first transaction. Quote what they actually pay.

Usage:
    cd sehaty-api
    uv run --extra print python scripts/sales_sheet.py --out ./print

French only, by design: this is the language of professional signage and
paperwork in Moroccan practice. (reportlab also cannot shape Arabic — see
`print_assets.py`.)
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

BRAND = HexColor("#2b73b3")
BRAND_DARK = HexColor("#1b3d5e")
BRAND_MINT = HexColor("#2fae9b")
MUTED = HexColor("#64748b")
LIGHT = HexColor("#f1f5f9")
HAIRLINE = Color(0.85, 0.87, 0.90)

CONTACT = "contact@sehaty.ma · sehaty.ma"

# Issuing company. PLACEHOLDERS — replace before printing anything a doctor
# keeps. The registration numbers are deliberately left as "à compléter" rather
# than filled with plausible digits: a fabricated RC or ICE on a commercial
# document reads as a real registration and is worse than an obvious blank.
COMPANY = {
    "name": "Agrogo SARL",
    "capital": "à compléter",
    "address": "à compléter, Casablanca",
    "rc": "à compléter",
    "ice": "à compléter",
    "if": "à compléter",
}

# Shown next to every price so the doctor knows the quoted figure is what they
# pay, and so the sheet matches the invoice they will receive.
TAX_NOTE = "Tous les prix sont TTC (TVA 20 % incluse)."

# (title, detail) — the seven things the 600 DH actually buys.
DELIVERABLES = [
    (
        "Votre page web professionnelle",
        "Nom, photo, spécialité, adresse, plan, horaires, tarif, langues et "
        "assurances acceptées. En français, arabe et darija. Boutons Appeler, "
        "WhatsApp et Itinéraire.",
    ),
    (
        "Votre plaque QR pour la salle d'attente",
        "Format A5, imprimée et plastifiée. Le patient scanne, il arrive sur votre page.",
    ),
    (
        "100 cartes de poche avec le même QR",
        "Pour le bureau de la secrétaire et le comptoir d'accueil.",
    ),
    (
        "Votre fiche Google corrigée",
        "Création ou réclamation : bons horaires, bonne adresse, bon téléphone, "
        "bonne catégorie, photos, lien vers votre page.",
    ),
    (
        "Vos photos de cabinet",
        "4 à 6 photos prises sur place et retouchées.",
    ),
    (
        "Votre référencement dans l'annuaire",
        "Vous apparaissez sur sehaty.ma/casablanca/<votre spécialité>, en "
        "position prioritaire pendant 12 mois.",
    ),
    (
        "Vos statistiques chaque mois, par WhatsApp",
        "Combien de vues, combien de clics Appeler, combien d'itinéraires demandés.",
    ),
]

NOT_INCLUDED = [
    "Pas de réservation en ligne pour l'instant — c'est prévu, et c'est offert "
    "3 mois le jour où votre agenda est activé.",
    "Pas de publicité payante.",
    "Pas de nom de domaine personnel : votre page est sur sehaty.ma. C'est un "
    "avantage — elle profite du référencement de tout l'annuaire, une page "
    "isolée ne remonte jamais sur Google.",
    "Aucune garantie de nouveaux patients. Personne ne peut vous la donner honnêtement.",
]

OBJECTIONS = [
    (
        "« J'ai déjà assez de patients. »",
        "Très bien. Alors ceci ne sert pas à en trouver : ça sert à ce que ceux "
        "qui vous cherchent déjà tombent sur les bonnes informations. Votre "
        "fiche Google affiche encore l'ancien numéro — je vous montre ?",
    ),
    (
        "« J'ai déjà Dabadoc / une page Facebook. »",
        "Gardez-les. Ceci ne les remplace pas. La différence : ici vous avez "
        "une vraie page indexée sur Google, une plaque physique dans la salle "
        "d'attente, et vos chiffres chaque mois.",
    ),
    (
        "« C'est cher. »",
        "Un développeur freelance facture 2 000 à 5 000 DH pour un site basique, "
        "plus l'hébergement chaque année. Ici c'est 600 DH TTC, une seule fois, "
        "livré en 48 heures, fiche Google comprise.",
    ),
    (
        "« Je vais réfléchir. »",
        "Bien sûr. Le tarif fondateur à 199 DH est réservé aux 30 premiers "
        "médecins de Casablanca — je vous le bloque jusqu'à vendredi, sans "
        "engagement de votre part aujourd'hui.",
    ),
    (
        "« Qui va voir cette page ? »",
        "Les patients qui cherchent « <votre spécialité> Casablanca » sur "
        "Google, et tous ceux qui scannent la plaque dans votre salle "
        "d'attente. Dans 3 mois je reviens avec les chiffres exacts.",
    ),
    (
        "« Et si je veux arrêter ? »",
        "Votre page reste en ligne gratuitement, à vie. L'abonnement s'arrête "
        "quand vous voulez, et vous gardez la plaque et les cartes : vous les "
        "avez payées, elles sont à vous.",
    ),
]


def wrap(pdf: canvas.Canvas, text: str, font: str, size: float, max_w: float) -> list[str]:
    """Greedy word-wrap — reportlab's canvas has no paragraph flow of its own."""
    pdf.setFont(font, size)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if pdf.stringWidth(candidate, font, size) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_paragraph(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_w: float,
    *,
    font: str = "Helvetica",
    size: float = 9.5,
    leading: float = 12,
    color: Color = MUTED,
) -> float:
    """Draw wrapped text downward from ``y``; return the new baseline."""
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    for line in wrap(pdf, text, font, size, max_w):
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _header(pdf: canvas.Canvas, width: float, height: float) -> None:
    pdf.setFillColor(BRAND)
    pdf.rect(0, height - 10 * mm, width, 10 * mm, stroke=0, fill=1)
    mark = 7 * mm
    x, y = 18 * mm, height - 25 * mm
    pdf.roundRect(x, y, mark, mark, mark * 0.28, stroke=0, fill=1)
    pdf.setFillColor(Color(1, 1, 1))
    bar = mark * 0.14
    pdf.rect(x + mark / 2 - bar / 2, y + mark * 0.24, bar, mark * 0.52, stroke=0, fill=1)
    pdf.rect(x + mark * 0.24, y + mark / 2 - bar / 2, mark * 0.52, bar, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(x + mark * 1.5, y + mark * 0.22, "Sehaty")


def _footer(pdf: canvas.Canvas, width: float) -> None:
    pdf.setStrokeColor(BRAND_MINT)
    pdf.setLineWidth(1)
    pdf.line(18 * mm, 20 * mm, width - 18 * mm, 20 * mm)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 8.5)
    pdf.drawCentredString(width / 2, 15 * mm, CONTACT)
    # Legal mentions of the issuing company — a commercial document a doctor
    # keeps should say who is billing them.
    pdf.setFont("Helvetica", 7)
    pdf.drawCentredString(
        width / 2,
        10.5 * mm,
        f"{COMPANY['name']} — {COMPANY['address']} — "
        f"RC {COMPANY['rc']} — ICE {COMPANY['ice']} — IF {COMPANY['if']}",
    )
    pdf.drawCentredString(width / 2, 7 * mm, TAX_NOTE)


def draw_recto(pdf: canvas.Canvas) -> None:
    """The offer."""
    width, height = A4
    left = 18 * mm
    content_w = width - 2 * left

    _header(pdf, width, height)

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(left, height - 42 * mm, "Pack Présence")

    # Price, with the list price struck through so 500 reads as the discount.
    pdf.setFont("Helvetica-Bold", 20)
    pdf.setFillColor(BRAND)
    pdf.drawString(left, height - 53 * mm, "600 DH TTC")
    pdf.setFont("Helvetica", 11)
    pdf.setFillColor(MUTED)
    paid_w = pdf.stringWidth("600 DH TTC", "Helvetica-Bold", 20)
    pdf.drawString(left + paid_w + 4 * mm, height - 53 * mm, "une seule fois")
    once_w = pdf.stringWidth("une seule fois", "Helvetica", 11)
    struck_x = left + paid_w + 4 * mm + once_w + 4 * mm
    pdf.drawString(struck_x, height - 53 * mm, "au lieu de 900 DH")
    struck_w = pdf.stringWidth("au lieu de 900 DH", "Helvetica", 11)
    pdf.setStrokeColor(MUTED)
    pdf.setLineWidth(0.7)
    pdf.line(struck_x, height - 52 * mm, struck_x + struck_w, height - 52 * mm)

    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(left, height - 59 * mm, TAX_NOTE)

    y = height - 68 * mm
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left, y, "Ce que vous recevez")
    y -= 8 * mm

    for index, (title, detail) in enumerate(DELIVERABLES, start=1):
        pdf.setFillColor(BRAND)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, f"{index}.")
        pdf.setFillColor(BRAND_DARK)
        pdf.drawString(left + 6 * mm, y, title)
        y -= 5 * mm
        y = draw_paragraph(pdf, detail, left + 6 * mm, y, content_w - 6 * mm)
        y -= 2.5 * mm

    # Delivery promise.
    pdf.setFillColor(LIGHT)
    pdf.roundRect(left, y - 13 * mm, content_w, 12 * mm, 2 * mm, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(
        left + 5 * mm,
        y - 8 * mm,
        "Livraison : votre page en ligne sous 48 heures.  Votre temps : 15 minutes aujourd'hui.",
    )
    y -= 20 * mm

    # The trial + subscription, framed so the founding rate is the anchor.
    pdf.setStrokeColor(BRAND_MINT)
    pdf.setLineWidth(1.2)
    pdf.roundRect(left, y - 36 * mm, content_w, 35 * mm, 3 * mm, stroke=1, fill=0)

    pdf.setFillColor(BRAND_MINT)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left + 5 * mm, y - 8 * mm, "Inclus : 3 mois d'agenda automatisé offerts")
    inner_y = draw_paragraph(
        pdf,
        "Réservation en ligne, confirmation WhatsApp automatique 24 h avant "
        "chaque rendez-vous, écran secrétaire, liste d'attente. Les 3 mois "
        "commencent le jour où votre agenda est activé — pas le jour du paiement.",
        left + 5 * mm,
        y - 14 * mm,
        content_w - 10 * mm,
    )

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(
        left + 5 * mm,
        inner_y - 2 * mm,
        "Ensuite : 199 DH TTC/mois — tarif fondateur bloqué 24 mois (au lieu de 349 DH).",
    )
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        left + 5 * mm,
        inner_y - 7 * mm,
        "Réglé au trimestre (597 DH TTC) ou à l'année (1 990 DH TTC, 2 mois "
        "offerts). Vous arrêtez quand vous voulez.",
    )

    _footer(pdf, width)
    pdf.showPage()


def draw_verso(pdf: canvas.Canvas) -> None:
    """What is not included, and the objections you will actually hear."""
    width, height = A4
    left = 18 * mm
    content_w = width - 2 * left

    _header(pdf, width, height)

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, height - 40 * mm, "Ce qui n'est pas inclus")

    y = height - 49 * mm
    for item in NOT_INCLUDED:
        pdf.setFillColor(BRAND)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, "—")
        y = draw_paragraph(pdf, item, left + 6 * mm, y, content_w - 6 * mm)
        y -= 2.5 * mm

    y -= 4 * mm
    pdf.setStrokeColor(HAIRLINE)
    pdf.setLineWidth(0.6)
    pdf.line(left, y, width - left, y)
    y -= 10 * mm

    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, y, "Ce qu'on vous dira, et quoi répondre")
    y -= 10 * mm

    for question, answer in OBJECTIONS:
        pdf.setFillColor(BRAND)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(left, y, question)
        y -= 5 * mm
        y = draw_paragraph(pdf, answer, left + 4 * mm, y, content_w - 4 * mm)
        y -= 4 * mm

    # The one question to open with — it qualifies the doctor and sizes the
    # subscription pitch at the same time.
    pdf.setFillColor(LIGHT)
    pdf.roundRect(left, y - 17 * mm, content_w, 16 * mm, 2 * mm, stroke=0, fill=1)
    pdf.setFillColor(BRAND_DARK)
    pdf.setFont("Helvetica-Bold", 10.5)
    pdf.drawString(left + 5 * mm, y - 7 * mm, "La question à poser en premier :")
    pdf.setFillColor(BRAND)
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(
        left + 5 * mm,
        y - 13 * mm,
        "« Combien de patients ne viennent pas, par semaine ? »",
    )

    _footer(pdf, width)
    pdf.showPage()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Pack Présence one-pager.")
    parser.add_argument("--out", type=Path, default=Path("print"), help="Output directory")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "pack-presence.pdf"

    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.setTitle("Sehaty — Pack Présence")
    draw_recto(pdf)
    draw_verso(pdf)
    pdf.save()

    print(f"sales sheet: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
