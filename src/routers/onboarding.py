"""Onboarding a doctor at the cabinet: find them, or add them.

Search first, deliberately. Most doctors are already on the platform from the
public-directory import, and creating a second profile for someone who has one
splits their reviews and orphans whatever QR code exists.
"""

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.onboarding import DoctorMatch, OnboardingController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.onboarding import CreateDoctorIn

router = APIRouter(prefix="/api/v1/admin/onboarding", tags=["onboarding"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/search", response_model=list[DoctorMatch])
def search_doctors(
    q: str = Query(min_length=2),
    limit: int = Query(default=12, ge=1, le=50),
    _admin: User = Depends(_require_admin),
) -> list[DoctorMatch]:
    """Doctors whose name looks like what was typed, unclaimed ones first."""
    return OnboardingController.search(q, limit=limit)


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
