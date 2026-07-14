"""Availability router. Body of each handler: parse -> ONE controller call.

No SQLAlchemy here. DOCTOR-only self-service management of the recurring weekly
windows from which bookable slots are derived. Business errors (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

from fastapi import APIRouter, Depends, Response, status
from sehaty.core.controllers.availability import AvailabilityController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.availability import AvailabilityIn, AvailabilityOut

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
