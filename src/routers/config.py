"""Admin configuration router — ranking weights + feature flags. Body of each
handler: parse -> ONE controller call -> return.

No SQLAlchemy here. Every route is gated to ``UserRole.ADMIN`` via
``require_roles``; business errors raised by ``ConfigController`` (the SehatyError
taxonomy, e.g. an unknown weight or negative value -> 422) are mapped to HTTP by
the global exception handler in ``main``.

The ranking-weights update is a partial PATCH-in-a-PUT: ``RankingWeightsIn``
leaves every field optional and the handler forwards only what the client sent
(``model_dump(exclude_unset=True)``), so unspecified weights stay untouched.
"""

from fastapi import APIRouter, Depends
from sehaty.core.controllers.config import ConfigController, RankingWeightsValues
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.config import (
    FeatureFlagIn,
    FeatureFlagOut,
    FeatureFlagsOut,
    RankingWeightsIn,
)

router = APIRouter(prefix="/api/v1/admin/config", tags=["config"])

_require_admin = require_roles(UserRole.ADMIN)


@router.get("/ranking-weights", response_model=RankingWeightsValues)
def get_ranking_weights(
    _admin: User = Depends(_require_admin),
) -> RankingWeightsValues:
    """The live doctor-locator ranking weights (defaults until an admin tunes them)."""
    return ConfigController.get_ranking_weights()


@router.put("/ranking-weights", response_model=RankingWeightsValues)
def set_ranking_weights(
    body: RankingWeightsIn,
    admin: User = Depends(_require_admin),
) -> RankingWeightsValues:
    """Update one or more ranking weights, leaving the rest untouched.

    Only the fields the client actually sent are forwarded; unset weights are
    not passed through, so the controller preserves their current values.
    """
    return ConfigController.set_ranking_weights(
        admin_id=admin.id, **body.model_dump(exclude_unset=True)
    )


@router.get("/feature-flags", response_model=FeatureFlagsOut)
def list_feature_flags(
    _admin: User = Depends(_require_admin),
) -> FeatureFlagsOut:
    """Every feature flag as a ``{key: enabled}`` mapping."""
    flags = ConfigController.list_feature_flags()
    return FeatureFlagsOut(flags=flags)


@router.put("/feature-flags/{key}", response_model=FeatureFlagOut)
def set_feature_flag(
    key: str,
    body: FeatureFlagIn,
    admin: User = Depends(_require_admin),
) -> FeatureFlagOut:
    """Create or flip a named feature flag."""
    flag = ConfigController.set_feature_flag(admin.id, key, body.enabled)
    return FeatureFlagOut.model_validate(flag)
