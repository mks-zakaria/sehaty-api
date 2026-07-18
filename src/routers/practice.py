"""Practice-profile (letterhead) router. Body of each handler: parse -> ONE
controller call -> return.

No SQLAlchemy here. A doctor keeps one or more letterheads (one per location)
used to render printable prescriptions; exactly one is the default (the
single-default invariant lives in ``PracticeProfileController``). Every route is
DOCTOR-scoped: the caller's own user id is the ``doctor_id``, so a profile
belonging to another doctor is a 404. Business errors (the SehatyError taxonomy)
are mapped to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.practice import PracticeProfileController, PracticeProfileRow
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import (
    PracticeProfileIn,
    PracticeProfileUpdateIn,
)

router = APIRouter(prefix="/api/v1/doctor/practice-profiles", tags=["practice-profiles"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=list[PracticeProfileRow])
def list_profiles(
    doctor: User = Depends(_require_doctor),
) -> list[PracticeProfileRow]:
    """The calling doctor's letterheads, the default first then oldest first."""
    return PracticeProfileController.list_for(doctor.id)


@router.post("", response_model=PracticeProfileRow, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: PracticeProfileIn,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileRow:
    """Create a letterhead (the doctor's FIRST profile is forced default)."""
    return PracticeProfileController.create(doctor.id, **body.model_dump())


@router.patch("/{profile_id}", response_model=PracticeProfileRow)
def update_profile(
    profile_id: int,
    body: PracticeProfileUpdateIn,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileRow:
    """Update the doctor's own letterhead (404 if not theirs).

    Only the fields the client actually sent are forwarded
    (``model_dump(exclude_unset=True)``), so an omitted field is left untouched.
    """
    return PracticeProfileController.update(
        doctor.id, profile_id, **body.model_dump(exclude_unset=True)
    )


@router.post("/{profile_id}/default", response_model=PracticeProfileRow)
def set_default_profile(
    profile_id: int,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileRow:
    """Make ``profile_id`` the doctor's one and only default (404 if not theirs)."""
    return PracticeProfileController.set_default(doctor.id, profile_id)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    doctor: User = Depends(_require_doctor),
) -> None:
    """Delete the doctor's own letterhead (404 if not theirs); promotes a survivor."""
    PracticeProfileController.delete(doctor.id, profile_id)
