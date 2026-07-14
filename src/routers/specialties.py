"""Specialties router. Body of each handler: parse -> ONE controller call ->
return.

No SQLAlchemy here. The medical-specialties catalogue is a small, public,
mostly-static lookup consumed by the marketplace and the doctor profile editor.
"""

from fastapi import APIRouter
from sehaty.core.controllers.specialties import SpecialtyController

from schemas.doctors import SpecialtyOut

router = APIRouter(prefix="/api/v1/specialties", tags=["specialties"])


@router.get("", response_model=list[SpecialtyOut])
def list_specialties() -> list[SpecialtyOut]:
    """Return the whole specialties catalogue, ordered by English name."""
    return [SpecialtyOut.model_validate(s) for s in SpecialtyController.list_specialties()]
