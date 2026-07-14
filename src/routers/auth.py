"""Auth router. Body of each handler: parse -> ONE controller call -> return.

No SQLAlchemy here. Business errors raised by the controller (the SehatyError
taxonomy) are mapped to HTTP by the global exception handler in `main`.
"""

import os

from fastapi import APIRouter, Depends, Request, Response, status
from sehaty.core.controllers.auth import AuthController
from sehaty.core.controllers.referral import ReferralController
from sehaty.db import User

from deps import get_current_user
from schemas.auth import (
    DoctorRegisterIn,
    LoginIn,
    MeOut,
    OtpRequestIn,
    OtpVerifyIn,
    RefreshIn,
    TokenOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/doctor/register", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def register_doctor(body: DoctorRegisterIn) -> MeOut:
    """Register a doctor (created unverified). Parse -> controller -> serialize.

    An optional ``referral_code`` links the new doctor to a referrer as a
    PENDING referral. Capture is non-fatal: an unknown/self/duplicate code
    returns ``None`` from core and never fails registration.
    """
    user = AuthController.register_doctor(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        slug=body.slug,
        license_no=body.license_no,
        phone=body.phone,
    )
    if body.referral_code:
        ReferralController.record_referral(body.referral_code, user.id)
    return MeOut.model_validate(user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request) -> TokenOut:
    """Email/password login → access + refresh token pair."""
    bundle = AuthController.login(
        body.email, body.password, user_agent=request.headers.get("user-agent")
    )
    return TokenOut(**bundle)


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
def request_otp(body: OtpRequestIn) -> dict:
    """Request a phone OTP for passwordless patient auth.

    The code is delivered out-of-band (SMS) and never returned in prod; in a
    ``SEHATY_ENV=dev`` environment it is echoed back to ease local testing.
    """
    code = AuthController.request_patient_otp(body.phone)
    payload: dict = {"sent": True}
    if os.environ.get("SEHATY_ENV") == "dev":
        payload["code"] = code
    return payload


@router.post("/otp/verify", response_model=TokenOut)
def verify_otp(body: OtpVerifyIn, request: Request) -> TokenOut:
    """Verify a phone OTP and log the patient in → token pair."""
    bundle = AuthController.verify_patient_otp_and_login(
        body.phone, body.code, user_agent=request.headers.get("user-agent")
    )
    return TokenOut(**bundle)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn) -> TokenOut:
    """Rotate a refresh token → fresh access + refresh pair."""
    bundle = AuthController.refresh(body.refresh)
    return TokenOut(**bundle)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshIn) -> Response:
    """Revoke a single refresh token (idempotent)."""
    AuthController.logout(body.refresh)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user)) -> MeOut:
    """Return the authenticated user's identity (bearer token required)."""
    return MeOut.model_validate(user)
