"""Auth dependencies for the API transport layer.

Bearer-token authentication that reuses `sehaty.core` primitives:

* `get_current_user` decodes the JWT with `security.decode_token` and loads the
  active user via `AuthController.get_active_user`;
* `require_roles` gates a route to one or more `UserRole`s;
* `require_verified` gates a doctor route on `DoctorProfile.verification_status`
  being `VERIFIED` (verification lives on the profile, never on `User`).

Business logic stays in the controller; these are thin authorization guards.
"""

from collections.abc import Callable

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sehaty.core import security
from sehaty.core.controllers.admin import AdminController
from sehaty.core.controllers.assistants import AssistantController
from sehaty.core.controllers.auth import AuthController
from sehaty.core.errors import SehatyForbiddenError
from sehaty.db import User, UserRole

# tokenUrl points at the password login so the OpenAPI "Authorize" flow works.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(token: str = Depends(_oauth2_scheme)) -> User:
    """Resolve the bearer token to an active `User` (401 on an invalid token)."""
    claims = security.decode_token(token)
    if claims is None or "sub" not in claims:
        raise _UNAUTHORIZED
    try:
        user_id = int(claims["sub"])
    except (TypeError, ValueError) as exc:
        raise _UNAUTHORIZED from exc
    # Raises SehatyForbiddenError (→ 403) if the account is missing/disabled.
    return AuthController.get_active_user(user_id)


def require_roles(*roles: UserRole) -> Callable[[User], User]:
    """Build a dependency that admits only users holding one of ``roles``."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise SehatyForbiddenError("insufficient role")
        return user

    return _guard


_require_doctor = require_roles(UserRole.DOCTOR)


def require_verified(user: User = Depends(_require_doctor)) -> User:
    """Admit only a DOCTOR whose profile is ``VERIFIED``.

    The verification rule lives in one place — ``AdminController`` — so this
    guard stays a thin, DB-free authorization check (no SQLAlchemy in the deps
    layer).
    """
    if not AdminController.is_doctor_verified(user.id):
        raise SehatyForbiddenError("doctor is not verified")
    return user


def get_acting_doctor_id(
    doctor_id: int | None = Query(default=None),
    user: User = Depends(get_current_user),
) -> int:
    """Resolve the effective ``doctor_id`` whose workspace the caller acts on.

    A DOCTOR gets their own id; an ASSISTANT gets the linked doctor's id (an
    optional ``doctor_id`` query param disambiguates when the assistant serves
    several doctors). The single resolution rule lives in
    ``AssistantController.resolve_doctor_id`` — any Forbidden/Validation it
    raises is mapped to HTTP by the global handler in ``main``. Other routers
    (booking/confirm) reuse this dependency so an assistant can drive the
    existing doctor-scoped controllers with the resolved id.
    """
    return AssistantController.resolve_doctor_id(user.id, user.role, requested_doctor_id=doctor_id)
