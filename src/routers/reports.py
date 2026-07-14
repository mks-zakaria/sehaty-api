"""Admin reporting + year-end accounting router. Body of each handler: parse ->
ONE controller call -> return.

No SQLAlchemy here. Every route is gated to ``UserRole.ADMIN`` via
``require_roles``. Two audiences share one ``ReportingController``: a live
operational KPI snapshot and a comptabilité trail. ``ReportingController`` does
all the aggregation and returns detached projections; the router only translates
them to the wire — including the one transport-shaped output, the accounting
export, which it serialises into a downloadable CSV (the controller returns the
ordered rows; the CSV framing is a transport concern that stays here).
"""

import csv
import io
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sehaty.core.controllers.reporting import ReportingController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.report import KpisOut, RevenueSummaryOut

router = APIRouter(prefix="/api/v1/admin/reports", tags=["reports"])

_require_admin = require_roles(UserRole.ADMIN)

# The stable comptabilité column set, in order.
_CSV_COLUMNS = ["date", "kind", "reference", "doctor_id", "amount", "currency", "detail"]


@router.get("/kpis", response_model=KpisOut)
def get_kpis(
    _admin: User = Depends(_require_admin),
) -> KpisOut:
    """The current operational KPIs for the admin dashboard."""
    kpis = ReportingController.kpis()
    return KpisOut.model_validate(kpis)


@router.get("/revenue", response_model=RevenueSummaryOut)
def get_revenue(
    year: int = Query(default_factory=lambda: datetime.now(UTC).year),
    _admin: User = Depends(_require_admin),
) -> RevenueSummaryOut:
    """A fiscal year's cash summary (defaults to the current year when omitted)."""
    summary = ReportingController.revenue_summary(year)
    return RevenueSummaryOut.model_validate(summary)


@router.get("/accounting-export")
def get_accounting_export(
    year: int = Query(default_factory=lambda: datetime.now(UTC).year),
    _admin: User = Depends(_require_admin),
) -> StreamingResponse:
    """Stream the immutable, date-ordered accounting trail for ``year`` as CSV.

    The controller returns the ordered ledger rows; here we frame them into a
    downloadable ``text/csv`` attachment with the stable comptabilité column set.
    """
    rows = ReportingController.accounting_export(year)

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.date.isoformat(),
                row.kind,
                row.reference,
                row.doctor_id,
                row.amount,
                row.currency,
                row.detail,
            ]
        )
    buffer.seek(0)

    filename = f"sehaty-accounting-{year}.csv"
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
