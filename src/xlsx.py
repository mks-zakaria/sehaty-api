"""Minimal dependency-free ``.xlsx`` writer (stdlib only).

Builds a real multi-sheet OpenXML workbook with ``zipfile`` + inline-string cells
— no openpyxl/xlsxwriter needed, works offline. Enough for the doctor data export
(the CSV framing of the accounting report has a sibling here for spreadsheets).
Numbers are written as numeric cells; everything else is an inline string.
"""

import zipfile
from collections.abc import Sequence
from io import BytesIO
from xml.sax.saxutils import escape

# One sheet = (title, column headers, data rows). A cell is a scalar.
Sheet = tuple[str, Sequence[str], Sequence[Sequence[object]]]

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels"'
    ' ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml"'
    ' ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    "{overrides}"
    "</Types>"
)
_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1"'
    ' Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"'
    ' Target="xl/workbook.xml"/></Relationships>'
)
_WORKBOOK = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
    "<sheets>{sheets}</sheets></workbook>"
)
_WB_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    "{rels}</Relationships>"
)
_WORKSHEET_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
_WORKSHEET_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"


def _col_letter(n: int) -> str:
    """1 → A, 26 → Z, 27 → AA (Excel column reference for a 1-based index)."""
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _clean(text: str) -> str:
    """Drop the control chars XML 1.0 forbids (keep tab/newline/carriage return)."""
    return "".join(c for c in text if c >= " " or c in "\t\n\r")


def _cell(ref: str, value: object) -> str:
    if value is None or value == "":
        return f'<c r="{ref}"/>'
    if isinstance(value, bool):
        return f'<c r="{ref}"><v>{int(value)}</v></c>'
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"><v>{value}</v></c>'
    text = escape(_clean(str(value)))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _worksheet(columns: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    lines = [
        "<row r=\"1\">"
        + "".join(_cell(f"{_col_letter(i + 1)}1", col) for i, col in enumerate(columns))
        + "</row>"
    ]
    for ri, row in enumerate(rows, start=2):
        cells = "".join(_cell(f"{_col_letter(ci + 1)}{ri}", v) for ci, v in enumerate(row))
        lines.append(f'<row r="{ri}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(lines)}</sheetData></worksheet>"
    )


def _safe_name(name: str) -> str:
    """A valid Excel sheet name: no forbidden chars, ≤ 31 chars, never blank."""
    for ch in r"[]:*?/\\":
        name = name.replace(ch, " ")
    return (name.strip() or "Sheet")[:31]


def build_xlsx(sheets: Sequence[Sheet]) -> bytes:
    """Render ``sheets`` into ``.xlsx`` bytes (a valid OpenXML workbook)."""
    if not sheets:
        sheets = [("Sheet1", [], [])]
    n = len(sheets)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="{_WORKSHEET_CT}"/>'
            for i in range(1, n + 1)
        )
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES.format(overrides=overrides))
        zf.writestr("_rels/.rels", _ROOT_RELS)
        sheet_tags = "".join(
            f'<sheet name="{escape(_safe_name(title))}" sheetId="{i}" r:id="rId{i}"/>'
            for i, (title, _cols, _rows) in enumerate(sheets, start=1)
        )
        zf.writestr("xl/workbook.xml", _WORKBOOK.format(sheets=sheet_tags))
        rels = "".join(
            f'<Relationship Id="rId{i}" Type="{_WORKSHEET_REL}" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, n + 1)
        )
        zf.writestr("xl/_rels/workbook.xml.rels", _WB_RELS.format(rels=rels))
        for i, (_title, columns, rows) in enumerate(sheets, start=1):
            zf.writestr(f"xl/worksheets/sheet{i}.xml", _worksheet(columns, rows))
    return buf.getvalue()
