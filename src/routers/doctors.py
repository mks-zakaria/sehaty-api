"""Doctors router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. Business errors raised by the controller (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.doctors import DoctorController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.doctors import DoctorOut, DoctorProfileIn, DoctorPublicOut

router = APIRouter(prefix="/api/v1/doctors", tags=["doctors"])

_require_doctor = require_roles(UserRole.DOCTOR)


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
