"""Request/response DTOs for the admin/accreditation surface.

No business logic, no DB access. Handlers call a single ``AdminController``
method and serialise the result back out. ``PendingProfessionalOut`` maps the
core ``PendingProfessional`` dataclass (from_attributes) onto the wire.
"""

from pydantic import BaseModel, ConfigDict


class PendingProfessionalOut(BaseModel):
    """A doctor awaiting accreditation, as returned to an admin."""

    model_config = ConfigDict(from_attributes=True)

    user_id: int
    full_name: str
    speciality: str | None = None
    license_no: str
    city: str | None = None
    email: str
