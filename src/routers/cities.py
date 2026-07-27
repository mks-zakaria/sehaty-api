"""Cities router — the browse axes behind the public landing pages.

The landing site calls these at build time to enumerate which ``/{city}`` and
``/{city}/{specialty}`` pages are worth generating, so a city with no verified
doctors never becomes a URL. Body of each handler: parse -> ONE controller call
-> return.

Every listing is derived from VERIFIED, active doctors only — the same
eligibility as the directory and the public doctor page. Slugs are accent-folded
(``Maârif`` -> ``maarif``); see ``sehaty.core.places``.
"""

from fastapi import APIRouter
from sehaty.core.controllers.cities import CityController, CitySpecialtyRef, PlaceRef

router = APIRouter(prefix="/api/v1/cities", tags=["cities"])


@router.get("", response_model=list[PlaceRef])
def list_cities() -> list[PlaceRef]:
    """Every city with at least one bookable doctor, busiest first."""
    return CityController.list_cities()


@router.get("/{city}/districts", response_model=list[PlaceRef])
def list_districts(city: str) -> list[PlaceRef]:
    """Neighbourhoods inside ``city`` that have doctors.

    An unknown city (or one where nobody recorded a district) returns ``[]``
    rather than 404: the city page still renders, just without the neighbourhood
    breakdown.
    """
    return CityController.list_districts(city)


@router.get("/{city}/specialties", response_model=list[CitySpecialtyRef])
def list_city_specialties(city: str) -> list[CitySpecialtyRef]:
    """Specialties practised in ``city``, most-served first.

    Each entry is guaranteed to have at least one doctor behind it, so the city
    hub never links to an empty specialty page.
    """
    return CityController.list_city_specialties(city)
