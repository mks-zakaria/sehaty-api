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
from sehaty.core.controllers.practice import PracticeProfileController
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.clinical import (
    PracticeProfileIn,
    PracticeProfileOut,
    PracticeProfileUpdateIn,
)

router = APIRouter(prefix="/api/v1/doctor/practice-profiles", tags=["practice-profiles"])

_require_doctor = require_roles(UserRole.DOCTOR)


@router.get("", response_model=list[PracticeProfileOut])
def list_profiles(
    doctor: User = Depends(_require_doctor),
) -> list[PracticeProfileOut]:
    """The calling doctor's letterheads, the default first then oldest first."""
    rows = PracticeProfileController.list_for(doctor.id)
    return [PracticeProfileOut.model_validate(r) for r in rows]


@router.post("", response_model=PracticeProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: PracticeProfileIn,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileOut:
    """Create a letterhead (the doctor's FIRST profile is forced default)."""
    row = PracticeProfileController.create(doctor.id, **body.model_dump())
    return PracticeProfileOut.model_validate(row)


@router.patch("/{profile_id}", response_model=PracticeProfileOut)
def update_profile(
    profile_id: int,
    body: PracticeProfileUpdateIn,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileOut:
    """Update the doctor's own letterhead (404 if not theirs).

    Only the fields the client actually sent are forwarded
    (``model_dump(exclude_unset=True)``), so an omitted field is left untouched.
    """
    row = PracticeProfileController.update(
        doctor.id, profile_id, **body.model_dump(exclude_unset=True)
    )
    return PracticeProfileOut.model_validate(row)


@router.post("/{profile_id}/default", response_model=PracticeProfileOut)
def set_default_profile(
    profile_id: int,
    doctor: User = Depends(_require_doctor),
) -> PracticeProfileOut:
    """Make ``profile_id`` the doctor's one and only default (404 if not theirs)."""
    row = PracticeProfileController.set_default(doctor.id, profile_id)
    return PracticeProfileOut.model_validate(row)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    doctor: User = Depends(_require_doctor),
) -> None:
    """Delete the doctor's own letterhead (404 if not theirs); promotes a survivor."""
    PracticeProfileController.delete(doctor.id, profile_id)
