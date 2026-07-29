"""Backup and restore for the directory, from the console.

Export is a download; restore is an upload with a dry run in front of it. Both
admin-only — this is the whole doctor table, including phone numbers.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.backup import (
    BackupController,
    BackupFile,
    RestoreReport,
)
from sehaty.db import User, UserRole

from deps import require_roles

router = APIRouter(prefix="/api/v1/admin/backup", tags=["backup"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("", response_model=BackupFile)
def export_backup(
    city: str | None = Query(default=None),
    _admin: User = Depends(_require_admin),
) -> BackupFile:
    """Everything worth keeping: pins, presentations, tariffs, hours, claims."""
    return BackupController.export(city=city)


@router.post("/restore", response_model=RestoreReport)
def restore_backup(
    payload: dict,
    dry_run: bool = Query(default=True),
    _admin: User = Depends(_require_admin),
) -> RestoreReport:
    """Put a backup back.

    Defaults to a dry run: an operator should see what would change before
    anything does. A blank in the file never clears a value, so restoring an old
    file cannot undo work done since.
    """
    return BackupController.restore(payload, dry_run=dry_run)
