"""Request/response DTOs for the auth surface — boundary translation only.

No business logic, no DB access. Handlers parse one of these, call a single
`AuthController` method, and serialise the result back out.
"""

from pydantic import BaseModel, ConfigDict


class DoctorRegisterIn(BaseModel):
    """Doctor self-registration: email + password credentials + licence."""

    email: str
    password: str
    full_name: str
    slug: str
    license_no: str
    phone: str | None = None


class LoginIn(BaseModel):
    """Email + password login (doctors/admins)."""

    email: str
    password: str


class OtpRequestIn(BaseModel):
    """Request a phone OTP for passwordless patient auth."""

    phone: str


class OtpVerifyIn(BaseModel):
    """Verify a phone OTP and exchange it for a token pair."""

    phone: str
    code: str


class RefreshIn(BaseModel):
    """Rotate a refresh token for a fresh access + refresh pair."""

    refresh: str


class TokenOut(BaseModel):
    """Access + refresh token pair with the authenticated role."""

    access: str
    refresh: str
    role: str


class MeOut(BaseModel):
    """The authenticated user's public identity."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    email: str | None = None
    phone: str | None = None
