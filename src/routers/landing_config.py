"""Admin control of a doctor's public landing page.

The template is chosen by staff during onboarding and changed from the console
afterwards — a doctor never picks their own. Content (acts, equipment, FAQ) is
captured in the same visit.

Body of each handler: parse -> ONE controller call -> return.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.doctors import DoctorController, DoctorView
from sehaty.core.controllers.landing_config import (
    KNOWN_TEMPLATES,
    LandingConfig,
    LandingConfigController,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.landing_config import (
    DoctorProfilePatchIn,
    LandingConfigIn,
    PersonalizedIn,
)

router = APIRouter(prefix="/api/v1/admin/doctors", tags=["landing-config"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/templates", response_model=list[str])
def list_templates(_admin: User = Depends(_require_admin)) -> list[str]:
    """Every template key the landing app can render, for the console picker."""
    return sorted(KNOWN_TEMPLATES)


@router.get("/{doctor_id}/landing", response_model=LandingConfig)
def get_landing(doctor_id: int, _admin: User = Depends(_require_admin)) -> LandingConfig:
    """The doctor's resolved configuration.

    ``template_is_default`` tells the console whether the template was inherited
    from the specialty or explicitly chosen, so staff can see what they are
    overriding.
    """
    return LandingConfigController.for_doctor(doctor_id)


@router.put("/{doctor_id}/landing", response_model=LandingConfig)
def update_landing(
    doctor_id: int,
    body: LandingConfigIn,
    _admin: User = Depends(_require_admin),
) -> LandingConfig:
    """Set the template and content. Omitted fields are left untouched."""
    return LandingConfigController.upsert(
        doctor_id,
        template=body.template,
        accent=body.accent,
        section_order=body.section_order,
        services=[s.model_dump() for s in body.services] if body.services is not None else None,
        equipment=body.equipment,
        faq=[f.model_dump() for f in body.faq] if body.faq is not None else None,
        tagline=body.tagline,
    )


@router.post("/{doctor_id}/landing/personalized", response_model=LandingConfig)
def set_personalized(
    doctor_id: int,
    body: PersonalizedIn,
    _admin: User = Depends(_require_admin),
) -> LandingConfig:
    """Record that the doctor is (or is no longer) on the paid page.

    Switching it off keeps their stored content, so a doctor who lapses and
    later resumes does not have to retype their services.
    """
    return LandingConfigController.set_personalized(doctor_id, enabled=body.enabled)


@router.get("/{doctor_id}/profile", response_model=DoctorView)
def get_profile(doctor_id: int, _admin: User = Depends(_require_admin)) -> DoctorView:
    """The doctor's full profile, whatever their verification status.

    Staff need to read a PENDING doctor's page while setting it up, which the
    public route deliberately refuses to do.
    """
    return DoctorController.get_for_admin(doctor_id)


@router.put("/{doctor_id}/profile", response_model=DoctorView)
def patch_profile(
    doctor_id: int,
    body: DoctorProfilePatchIn,
    _admin: User = Depends(_require_admin),
) -> DoctorView:
    """Fill in what was collected at the visit — hours, insurance, contact.

    Partial by design: only the fields present in the body are written. This is
    the only operator path to opening hours and insurance, which the importer
    cannot carry and which an imported doctor cannot enter themselves (they have
    no login).
    """
    DoctorController.patch_profile(
        doctor_id, **body.model_dump(exclude_unset=True, exclude_none=True)
    )
    return DoctorController.get_for_admin(doctor_id)
