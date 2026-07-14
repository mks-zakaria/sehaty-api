"""Doctors router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. Business errors raised by the controller (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.doctor_search import DoctorSearchController
from sehaty.core.controllers.doctors import DoctorController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.doctors import DoctorProfileIn, DoctorPublicOut, DoctorSearchResultOut

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=list[DoctorSearchResultOut])
def search_doctors(
    specialty: str = Query(..., description="Specialty slug to search within."),
    lat: float = Query(..., description="Search origin latitude."),
    lng: float = Query(..., description="Search origin longitude."),
    radius_m: int = Query(default=10000, description="Search radius in metres."),
    limit: int = Query(default=20, description="Maximum number of hits."),
) -> list[DoctorSearchResultOut]:
    """Public marketplace search: VERIFIED doctors of a specialty near a point.

    Returns hits ranked best-first (a weighted blend of rating + proximity),
    ties broken by distance. `specialty`, `lat`, `lng` are required; a missing
    one is a 422 from FastAPI, an out-of-range value a 400 from the controller's
    SehatyValidationError. Parse -> ONE controller call -> serialize.
    """
    results = DoctorSearchController.search(
        specialty_slug=specialty,
        lat=lat,
        lng=lng,
        radius_m=radius_m,
        limit=limit,
    )
    return [DoctorSearchResultOut.model_validate(r) for r in results]


@router.put("/me/profile")
def upsert_my_profile(
    body: DoctorProfileIn,
    user: User = Depends(_require_doctor),
) -> dict[str, str]:
    """Create or update the calling doctor's profile; returns its `{slug}`.

    DOCTOR-only. The profile stays PENDING until an admin accredits it, so a
    freshly written slug is not yet publicly resolvable via `GET /{slug}`.
    """
    slug = DoctorController.upsert_profile(user.id, **body.model_dump())
    return {"slug": slug}


@router.get("/{slug}", response_model=DoctorPublicOut)
def get_doctor(slug: str) -> DoctorPublicOut:
    """Public doctor page. 404 (via the SehatyError handler) when the slug is
    unknown or the doctor is not VERIFIED — unverified profiles are not leaked.
    """
    view = DoctorController.get_by_slug(slug)
    return DoctorPublicOut.model_validate(view)
