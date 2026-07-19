"""Doctor data-export router: stream the doctor's practice as an .xlsx download.

The core ``ExportController`` returns the ordered sheets (the data + scoping);
building the actual workbook file is a transport concern that stays here, mirroring
the CSV framing in ``routers/reports.py``.
"""

from fastapi import APIRouter, Depends, Response
from sehaty.core.controllers.export import ExportController
from sehaty.db import User, UserRole

from deps import require_roles
from xlsx import _XLSX_MEDIA, build_xlsx

router = APIRouter(prefix="/api/v1/doctor", tags=["export"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("/export.xlsx")
def export_doctor_data(user: User = Depends(_require_doctor)) -> Response:
    """Download the calling doctor's whole practice as a multi-sheet Excel workbook."""
    sheets = ExportController.doctor_export(user.id)
    content = build_xlsx([(s.title, s.columns, s.rows) for s in sheets])
    return Response(
        content=content,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": 'attachment; filename="sehaty-export.xlsx"'},
    )
