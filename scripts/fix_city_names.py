#!/usr/bin/env python
"""Correct city names already written into a harvest.

The scraper derived a display name by title-casing the slug, which produced
"Fes", "Tetouan", "Ait Melloul" and "Laayoune" — misspellings of real cities,
headed for the public page of every doctor in them. The scraper is fixed; this
repairs the files harvested before it was.

Idempotent, and only ever replaces a name with its accented form.

    uv run python scripts/fix_city_names.py doctors-*.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from scrape_doctors import CITY_NAMES

# Un-accented form -> the name a patient should actually read.
CORRECTIONS = {
    "Fes": "Fès",
    "Meknes": "Meknès",
    "Tetouan": "Tétouan",
    "Ait Melloul": "Aït Melloul",
    "Laayoune": "Laâyoune",
    "Khemisset": "Khémisset",
    "Beni Mellal": "Béni Mellal",
    "Sale": "Salé",
    "Temara": "Témara",
    "Ain Harrouda": "Aïn Harrouda",
}
# Anything the scraper itself now knows about, keyed by its stripped form.
CORRECTIONS.update(
    {name.encode("ascii", "ignore").decode(): name for name in CITY_NAMES.values()}
)


def main(paths: list[str]) -> int:
    for raw in paths:
        path = Path(raw)
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        if not rows:
            continue
        columns = list(rows[0])

        changed = 0
        for row in rows:
            for field in ("city", "district"):
                fixed = CORRECTIONS.get((row.get(field) or "").strip())
                if fixed and fixed != row[field]:
                    row[field] = fixed
                    changed += 1

        if changed:
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
        print(f"  {path.name}: {changed} corrected")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
