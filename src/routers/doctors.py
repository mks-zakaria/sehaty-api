"""Doctors router. Body of each handler: parse -> ONE controller call -> return.

Business errors raised by the controller (the SehatyError taxonomy) are mapped
to HTTP by the global exception handler in `main`.

Two public free-slot listings coexist, disambiguated by a Starlette path
converter so they never collide on ``/{x}/slots``:

* ``GET /{slug}/slots`` — the public, slug-keyed endpoint. It delegates to
  ``DoctorController.get_public_slots``, which resolves the slug to a VERIFIED
  doctor (404 otherwise, mirroring ``GET /{slug}``) and expands availability
  without ever loading the PostGIS ``geopoint``. This is the canonical public
  route.
* ``GET /{doctor_id:int}/slots`` — the pre-existing numeric-id route, kept for
  its current consumers (the booking flow / behaviour suite). It has no
  verification gate and opens a core-managed read session to the
  ``available_slots`` service directly — the one exception to "no SQLAlchemy",
  as there is still no slot controller for id-keyed lookups.

The ``:int`` converter (regex ``[0-9]+``) makes the numeric route match only
all-digit segments; every other segment (a slug) falls through to the string
route. The numeric route is declared first so a digits-only path binds to it.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sehaty.core.controllers.doctor_search import DoctorSearchController
from sehaty.core.controllers.doctors import DoctorController
from sehaty.core.db.session import get_session
from sehaty.core.services.slots import available_slots
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.appointments import SlotOut
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


@router.get("/{doctor_id:int}/slots", response_model=list[SlotOut])
def get_doctor_slots(
    doctor_id: int,
    from_date: date = Query(alias="from", description="First day of the range (inclusive)."),
    to_date: date = Query(alias="to", description="Last day of the range (inclusive)."),
) -> list[SlotOut]:
    """Public free-slot listing for a doctor across ``[from, to]`` (capped at 31d).

    Keyed by the doctor's numeric user id (see the module docstring); no
    verification gate. Expands the doctor's weekly availability into concrete UTC
    slots minus active bookings. The ``:int`` converter keeps this route from
    shadowing the slug-keyed one below.
    """
    with get_session() as session:
        slots = available_slots(session, doctor_id, from_date, to_date)
    return [SlotOut(start_at=start, end_at=end) for start, end in slots]


@router.get("/{slug}/slots", response_model=list[SlotOut])
def get_doctor_slots_by_slug(
    slug: str,
    from_date: date = Query(alias="from", description="First day of the range (inclusive)."),
    to_date: date = Query(alias="to", description="Last day of the range (inclusive)."),
) -> list[SlotOut]:
    """Public free-slot listing for a VERIFIED doctor, keyed by their slug.

    Delegates to ``DoctorController.get_public_slots``, which 404s (via the
    SehatyError handler) when the slug is unknown or the doctor is not VERIFIED —
    unverified profiles are not leaked — and otherwise expands the weekly
    availability into concrete UTC ``{start_at, end_at}`` slots minus active
    bookings across ``[from, to]``.
    """
    slots = DoctorController.get_public_slots(slug, from_date, to_date)
    return [SlotOut.model_validate(slot) for slot in slots]
