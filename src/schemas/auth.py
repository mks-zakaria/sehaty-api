"""Request/response DTOs for the auth surface — boundary translation only.

No business logic, no DB access. Handlers parse one of these, call a single
`AuthController` method, and serialise the result back out.
"""

from pydantic import BaseModel


class DoctorRegisterIn(BaseModel):
    """Doctor self-registration: email + password credentials + licence.

    ``referral_code`` is optional: when a referrer's code is supplied it links
    the new doctor as a PENDING referral. An unknown/self/duplicate code is a
    non-fatal no-op — registration always succeeds regardless.
    """

    email: str
    password: str
    full_name: str
    slug: str
    license_no: str
    phone: str | None = None
    referral_code: str | None = None


class PharmacyRegisterIn(BaseModel):
    """Pharmacy self-registration: email + password credentials."""

    email: str
    password: str
    phone: str | None = None


class PatientRegisterIn(BaseModel):
    """Patient self-registration: phone + password (no OTP for now)."""

    phone: str
    password: str


class PatientLoginIn(BaseModel):
    """Patient phone + password login."""

    phone: str
    password: str


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
