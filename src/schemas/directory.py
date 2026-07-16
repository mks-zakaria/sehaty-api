"""Response DTOs for the public doctor-directory browse surface.

Boundary translation only — no business logic, no DB access. These `*Out`
models mirror `sehaty.core`'s `DirectoryRow` / `DirectoryPage` dataclasses
one-to-one (the reputation join and specialty resolution happen in the
controller, never here) and translate them into the JSON contract clients
consume via `from_attributes`.
"""

from pydantic import BaseModel, ConfigDict


class DirectoryDoctorOut(BaseModel):
    """One doctor in the non-geo directory listing — mirrors `DirectoryRow`."""

    model_config = ConfigDict(from_attributes=True)

    slug: str
    full_name: str
    photo_url: str | None = None
    city: str | None = None
    consultation_fee: float | None = None
    avg_stars: float
    review_count: int
    specialties: list[str]


class DirectoryPageOut(BaseModel):
    """A page of directory rows plus the total match count — mirrors `DirectoryPage`."""

    model_config = ConfigDict(from_attributes=True)

    total: int
    doctors: list[DirectoryDoctorOut]
