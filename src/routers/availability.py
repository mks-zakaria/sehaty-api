"""Availability router. Body of each handler: parse -> ONE controller call.

No SQLAlchemy here. DOCTOR-only self-service management of the recurring weekly
windows from which bookable slots are derived. Business errors (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response, status
from sehaty.core.controllers.availability import AvailabilityController
from sehaty.core.controllers.availability_exceptions import AvailabilityExceptionController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.availability import (
    AvailabilityExceptionIn,
    AvailabilityExceptionOut,
    AvailabilityIn,
    AvailabilityOut,
)

router = APIRouter(prefix="/api/v1/doctors/me/availability", tags=["availability"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.post("", response_model=AvailabilityOut, status_code=status.HTTP_201_CREATED)
def add_availability(
    body: AvailabilityIn,
    user: User = Depends(_require_doctor),
) -> AvailabilityOut:
    """Add a recurring weekly availability window for the calling doctor."""
    avail = AvailabilityController.add(
        user.id,
        body.weekday,
        body.start_time,
        body.end_time,
        body.slot_minutes,
    )
    return AvailabilityOut.model_validate(avail)


@router.get("", response_model=list[AvailabilityOut])
def list_availability(user: User = Depends(_require_doctor)) -> list[AvailabilityOut]:
    """List the calling doctor's availability windows."""
    return [AvailabilityOut.model_validate(a) for a in AvailabilityController.list(user.id)]


@router.delete("/{availability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_availability(
    availability_id: int,
    user: User = Depends(_require_doctor),
) -> Response:
    """Delete one of the calling doctor's availability windows (ownership-checked)."""
    AvailabilityController.delete(user.id, availability_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/exceptions", response_model=list[AvailabilityExceptionOut])
def list_exceptions(
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    user: User = Depends(_require_doctor),
) -> list[AvailabilityExceptionOut]:
    """List the calling doctor's date-specific availability exceptions.

    ``date_from`` / ``date_to`` (inclusive) narrow the range when supplied.
    """
    rows = AvailabilityExceptionController.list(user.id, date_from=date_from, date_to=date_to)
    return [AvailabilityExceptionOut.model_validate(r) for r in rows]


@router.post(
    "/exceptions",
    response_model=AvailabilityExceptionOut,
    status_code=status.HTTP_201_CREATED,
)
def add_exception(
    body: AvailabilityExceptionIn,
    user: User = Depends(_require_doctor),
) -> AvailabilityExceptionOut:
    """Add a date-specific BLOCK/OPEN exception for the calling doctor."""
    row = AvailabilityExceptionController.add(
        user.id,
        body.date,
        body.kind,
        start_time=body.start_time,
        end_time=body.end_time,
        slot_minutes=body.slot_minutes,
        reason=body.reason,
    )
    return AvailabilityExceptionOut.model_validate(row)


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exception(
    exception_id: int,
    user: User = Depends(_require_doctor),
) -> Response:
    """Delete one of the calling doctor's exceptions (ownership-checked)."""
    AvailabilityExceptionController.delete(user.id, exception_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
