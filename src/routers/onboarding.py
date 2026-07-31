"""Onboarding a doctor at the cabinet: find them, or add them.

Search first, deliberately. Most doctors are already on the platform from the
public-directory import, and creating a second profile for someone who has one
splits their reviews and orphans whatever QR code exists.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.cities import PlaceRef
from sehaty.core.controllers.onboarding import DoctorMatch, OnboardingController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.onboarding import CreateDoctorIn

router = APIRouter(prefix="/api/v1/admin/onboarding", tags=["onboarding"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/cities", response_model=list[PlaceRef])
def list_cities(_admin: User = Depends(_require_admin)) -> list[PlaceRef]:
    """Cities the search filter can offer, busiest first.

    Wider than the public ``/api/v1/cities``: onboarding has to reach pages a
    patient never sees, so this counts every doctor the search can return.
    """
    return OnboardingController.cities()


@router.get("/search", response_model=list[DoctorMatch])
def search_doctors(
    q: str = Query(min_length=2),
    city: str | None = Query(default=None, description="city slug or display name"),
    limit: int = Query(default=12, ge=1, le=50),
    _admin: User = Depends(_require_admin),
) -> list[DoctorMatch]:
    """Doctors whose name looks like what was typed, unclaimed ones first.

    ``city`` narrows to one place — the operator's way of telling two Bennanis
    apart without reading twelve near-identical rows.
    """
    return OnboardingController.search(q, city=city, limit=limit)


@router.post("/doctors", response_model=DoctorMatch, status_code=201)
def create_doctor(body: CreateDoctorIn, _admin: User = Depends(_require_admin)) -> DoctorMatch:
    """Add a doctor the directory never had.

    Refuses a name that already exists in that city: the search above is there
    precisely so the operator lands on the existing page instead.
    """
    return OnboardingController.create(
        full_name=body.full_name,
        city=body.city,
        specialty_slug=body.specialty_slug,
        district=body.district,
        address=body.address,
    )
