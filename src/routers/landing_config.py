"""Admin control of a doctor's public landing page.

The template is chosen by staff during onboarding and changed from the console
afterwards — a doctor never picks their own. Content (acts, equipment, FAQ) is
captured in the same visit.

Body of each handler: parse -> ONE controller call -> return.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.landing_config import (
    KNOWN_TEMPLATES,
    LandingConfig,
    LandingConfigController,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.landing_config import LandingConfigIn, PersonalizedIn

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
