"""Cabinet + cabinet-session router. parse -> ONE controller call -> return.

No SQLAlchemy here. A doctor manages their cabinets and opens/closes shifts; an
open session means the acting doctor (owner or substitute) is "online" at the
cabinet. Business errors are mapped to HTTP by the handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.cabinet import CabinetController, CabinetRow, CabinetSessionRow
from sehaty.db import User, UserRole

from deps import get_acting_doctor_id, require_roles
from schemas.cabinet import AlertThresholdIn, CabinetIn, OpenSessionIn, WaitingCountIn

router = APIRouter(prefix="/api/v1/cabinets", tags=["cabinets"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.post("", response_model=CabinetRow, status_code=status.HTTP_201_CREATED)
def create_cabinet(body: CabinetIn, user: User = Depends(_require_doctor)) -> CabinetRow:
    """Create a cabinet owned by the calling doctor."""
    return CabinetController.create(user.id, body.name, body.address)


@router.get("", response_model=list[CabinetRow])
def list_cabinets(user: User = Depends(_require_doctor)) -> list[CabinetRow]:
    """List the calling doctor's cabinets."""
    return CabinetController.list_for_owner(user.id)


@router.post(
    "/{cabinet_id}/sessions",
    response_model=CabinetSessionRow,
    status_code=status.HTTP_201_CREATED,
)
def open_session(
    cabinet_id: int, body: OpenSessionIn, user: User = Depends(_require_doctor)
) -> CabinetSessionRow:
    """Open a shift at a cabinet — the acting doctor goes online (409 if one is open)."""
    return CabinetController.open_session(cabinet_id, body.acting_doctor_id or user.id)


@router.get("/{cabinet_id}/session", response_model=CabinetSessionRow | None)
def current_session(
    cabinet_id: int, user: User = Depends(_require_doctor)
) -> CabinetSessionRow | None:
    """The cabinet's currently-open session, or null when nobody is online."""
    return CabinetController.current_session(cabinet_id)


@router.post("/sessions/{session_id}/close", response_model=CabinetSessionRow)
def close_session(session_id: int, user: User = Depends(_require_doctor)) -> CabinetSessionRow:
    """Close a shift — the acting doctor goes offline."""
    return CabinetController.close_session(session_id)


@router.post("/{cabinet_id}/waiting-count", response_model=CabinetRow)
def set_waiting_count(
    cabinet_id: int,
    body: WaitingCountIn,
    acting_doctor_id: int = Depends(get_acting_doctor_id),
) -> CabinetRow:
    """Set the waiting-room head-count (doctor or their secretary).

    Crossing the doctor's threshold while nobody is online at the cabinet
    notifies the owner to head in.
    """
    return CabinetController.set_waiting_count(acting_doctor_id, cabinet_id, body.count)


@router.put("/{cabinet_id}/alert-threshold", response_model=CabinetRow)
def set_alert_threshold(
    cabinet_id: int,
    body: AlertThresholdIn,
    user: User = Depends(_require_doctor),
) -> CabinetRow:
    """Set (or clear) the calling doctor's waiting-room alert threshold."""
    return CabinetController.set_alert_threshold(user.id, cabinet_id, body.threshold)
