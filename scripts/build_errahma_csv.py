#!/usr/bin/env python
"""Build the Errahma / Dar Bouazza prospect CSV from directory listings.

Every row here was read off a public professional directory (Telecontact —
Morocco's yellow pages — cross-checked against e-rdv.ma and annuaire-horaire).
Nothing is inferred: a field the directory did not publish is left empty, which
the importer handles by rendering a shorter page. Fabricating a plausible phone
number or opening time would put wrong information on a real practitioner's
public listing, and would be found out on the first visit.

The generator is a script rather than a hand-typed file for one reason: the
addresses contain commas, and hand-writing CSV is how you silently spill a
column. ``csv.writer`` quotes them correctly.

Names are stored twice. Moroccan directories list SURNAME Firstname, which
reads wrong on a public page, so ``full_name`` flips it to "Dr Firstname
Surname". ``source_name`` keeps the directory string verbatim so any bad flip
is one grep away — see AMBIGUOUS below for the two worth eyeballing.

    uv run python scripts/build_errahma_csv.py > doctors-errahma.csv
"""

from __future__ import annotations

import csv
import sys

# Telecontact lists SURNAME Firstname. These two are names where both halves
# are plausible as either, so the flip is a guess — confirm on the visit.
AMBIGUOUS = {"Jalal Ayoub", "Zouhair Mohammed"}

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
    # Not read by the importer (it uses row.get), carried for provenance.
    "source_name",
    "source",
]

TC = "telecontact.ma"
ERDV = "e-rdv.ma"
AH = "ma.annuaire-horaire.com"
MED = "med.ma"

# (source_name, specialty, district, address, phone_fixe, source)
# district "Errahma" = the address names Rahma/Errahma/Arrahma in some spelling.
LISTINGS: list[tuple[str, str, str, str, str, str]] = [
    # ---- Dentists -------------------------------------------------------
    (
        "Aaflani Houda",
        "dentistry",
        "Errahma",
        "route de Rahma, lotiss. Acharaf GH 26, mmb. 4, appt. 2, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Bentass Sara",
        "dentistry",
        "Errahma",
        "76 lotiss. El Fath 2, GH12 rdc. appt. 2, Madinat Rahma, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Centre Dentaire Errahma",
        "dentistry",
        "Errahma",
        "Madinat Errahma, lotiss. 143, 1er ét. appt. 2, Dar Bouazza",
        "0522906302",
        TC,
    ),
    (
        "Guerram Imane",
        "dentistry",
        "Errahma",
        "lotiss. Madinat Errahma, lot 51, résid. Babel 5, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Haddou Ghizlane",
        "dentistry",
        "Errahma",
        "Madinat Errahma, bloc U2, n°21, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Hameddine Imane",
        "dentistry",
        "Errahma",
        "Madinat Errahma 2, résid. Rania 1, immb. 2, 2ème ét., Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Jalal Ayoub",
        "dentistry",
        "Errahma",
        "Madinate Arrahma 1, n°70 bloc 9, 1er ét., Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Khadraoui Wassila",
        "dentistry",
        "Errahma",
        "30 bd Nassrin, 1er ét., ville Rahma, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Mezzi Oumaima",
        "dentistry",
        "Errahma",
        "Madinat El Rahma, bloc 17, bd Alaymoune, 2ème ét. n°1, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Outegda Saida",
        "dentistry",
        "Errahma",
        "Madinat Errahma, bloc U4, n°107, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Sehbaoui Asmaa",
        "dentistry",
        "Errahma",
        "Jaouharat Errahma, imm. 9, GH/2, appt. n°1, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Z Bleu",
        "dentistry",
        "Errahma",
        "hay Madinat Arrahma, bloc 19, mag. n°25, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Amaddah Sara",
        "dentistry",
        "Dar Bouazza",
        "15 lotiss. Al Ansari, 1er ét., Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Benredouane Hamza",
        "dentistry",
        "Dar Bouazza",
        "route Moulay Thami, Achraf 2 GH6, 1er ét. appt. 6, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Centre Dentaire Dar Bouazza",
        "dentistry",
        "Dar Bouazza",
        "15 lotiss. Ansari, 1er ét., Dar Bouazza",
        "",
        TC,
    ),
    (
        "Fodda Myriam",
        "dentistry",
        "Dar Bouazza",
        "52 lotiss. Ansari, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Squalli Houssaini Samia",
        "dentistry",
        "Dar Bouazza",
        "123 lotiss. Ansari, Dar Bouazza",
        "",
        f"{TC}+{ERDV}",
    ),
    (
        "Zénith Dentistry Center",
        "dentistry",
        "Sidi Maârouf",
        "237 lotiss. Mandarona, hay Sidi Maârouf 1, 20520 Casablanca",
        "",
        TC,
    ),
    # ---- Generalists ----------------------------------------------------
    (
        "Affane Nissrine",
        "generalist",
        "Errahma",
        "hay Madinat Arrahma, résid. Al Amal, imm. 33, GH 04, appt. n°1, rdc, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Dehbi Abdelaziz",
        "generalist",
        "Errahma",
        "66 hay Madinat Arrahma, appt. n°1, rdc, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Elbali Nora",
        "generalist",
        "Errahma",
        "hay Arrahma, projet Miftah El Khir, GH3, imm. A, 2ème ét. appt. 6, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Lamrani Sanaa",
        "generalist",
        "Errahma",
        "hay Madinat Arrahma - Casablanca II, cmplx. Attawhid, GH22, "
        "imm. 149, rdc n°4, Dar Bouazza",
        "",
        TC,
    ),
    ("Merzaq Sofia", "generalist", "Errahma", "Madinat Errahma, bloc 4, n°96, Dar Bouazza", "", TC),
    (
        "Mzaalak Tazi Houda",
        "generalist",
        "Errahma",
        "Bassatine Errahma Extension, GH1, imm. 6, appt. n°1, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Saoui Abderrazak",
        "generalist",
        "Errahma",
        "6 résid. Lilas, jnane Rahma, GH1, 1er ét., appt. 6, Saada 1, Dar Bouazza",
        "",
        TC,
    ),
    (
        "Zouhair Mohammed",
        "generalist",
        "Errahma",
        "Madinat Errahma, bloc B lot 7, 1er ét., Dar Bouazza",
        "",
        TC,
    ),
    (
        "Centre Médical Mabrouk",
        "generalist",
        "Errahma",
        "Madinat Errahma, n°72, résid. Hajar, 1er ét., appt. 4, Dar Bouazza",
        "0522905577",
        TC,
    ),
    (
        "Cabinet Médical Madinat Arrahma",
        "generalist",
        "Errahma",
        "Madinat Arrahma, 26000 Casablanca",
        "0522657802",
        AH,
    ),
    ("Ansar Abdelkrim", "generalist", "Dar Bouazza", "28 lotiss. Littoral II, Dar Bouazza", "", TC),
    (
        "Benjabbour Hamza",
        "generalist",
        "Dar Bouazza",
        "K190 rte d'Azemmour, imm. C, km 19, Dar Bouazza",
        "",
        TC,
    ),
    ("Essarraj Houda", "generalist", "Dar Bouazza", "123 lotiss. Anssari, Dar Bouazza", "", TC),
    ("M'haidra Abdeladim", "generalist", "Dar Bouazza", "village pilote n°91, Dar Bouazza", "", TC),
    ("Mosseddaq Rabia", "generalist", "Dar Bouazza", "338 Village Pilote, Dar Bouazza", "", TC),
    # ---- Paediatrics ----------------------------------------------------
    (
        "Ghazali Dalila",
        "pediatrics",
        "Dar Bouazza",
        "résid. Le Littoral 2, imm. 20, 1er ét., Anssari, Dar Bouazza",
        "",
        TC,
    ),
    # ---- Address still to confirm on the visit ---------------------------
    # Specialty and quartier are stated by the directory; the street address
    # is not, so these three go out with an empty address rather than a
    # guessed one.
    ("Nora Azenkouk", "dentistry", "Errahma", "", "", MED),
    ("Benmalk Anass", "dentistry", "Dar Bouazza", "", "", MED),
    ("Bushra Abdulhakeem", "otolaryngology", "Errahma", "", "", "pharmacieenpermanence.ma"),
]


def display_name(source_name: str) -> str:
    """ "Aaflani Houda" -> "Dr Houda Aaflani"; practices keep their own name."""
    words = source_name.split()
    is_practice = any(
        w.lower() in {"centre", "cabinet", "center", "z", "zénith"} for w in words[:1]
    )
    if is_practice:
        return source_name
    # Surname is everything but the final token (compound surnames are common:
    # "Squalli Houssaini Samia", "Mzaalak Tazi Houda").
    if source_name in {"Nora Azenkouk", "Benmalk Anass", "Bushra Abdulhakeem"}:
        return f"Dr {source_name}"  # already first-name-first from the source
    *surname, first = words
    return f"Dr {first} {' '.join(surname)}"


def main() -> None:
    writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
    writer.writeheader()
    for source_name, specialty, district, address, phone, source in LISTINGS:
        writer.writerow(
            {
                "full_name": display_name(source_name),
                "specialty": specialty,
                "city": "Casablanca",
                "district": district,
                "address": address,
                "phone_fixe": phone,
                "source_name": source_name,
                "source": source,
            }
        )


if __name__ == "__main__":
    main()
