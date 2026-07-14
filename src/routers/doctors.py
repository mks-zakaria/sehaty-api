"""Doctors router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. Business errors raised by the controller (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

from fastapi import APIRouter, Query
from sehaty.core.controllers.doctors import DoctorController

from schemas.doctors import DoctorOut

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])


@router.get("", response_model=list[DoctorOut])
def search_doctors(
    specialty: str | None = Query(default=None),
    city: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
    limit: int = Query(default=20),
) -> list[DoctorOut]:
    """Marketplace doctor search.

    `specialty`, `lat`, `lng` are accepted at the boundary for the geo/faceted
    search the core will grow; today the controller filters by `city` (and a
    free-text `query`). Parse -> controller -> serialize.
    """
    profiles = DoctorController.search(
        city=city,
        query=specialty,
        limit=limit,
    )
    return [DoctorOut.model_validate(p) for p in profiles]
