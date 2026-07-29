"""Request DTOs for onboarding — boundary translation only."""

from pydantic import BaseModel


class CreateDoctorIn(BaseModel):
    """A doctor the search could not find."""

    full_name: str
    city: str
    specialty_slug: str
    district: str | None = None
    address: str | None = None
