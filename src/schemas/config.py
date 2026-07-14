"""Request/response DTOs for the admin configuration surface.

No business logic, no DB access. These models translate the frozen projection
dataclasses returned by ``sehaty.core``'s ``ConfigController``
(``RankingWeightsValues``, ``FeatureFlagValue``) into the JSON contract the admin
console consumes, and validate the admin's mutations on the way in.

``RankingWeightsIn`` leaves every weight optional so a client can PATCH a single
knob; the router forwards only the fields actually sent (``exclude_unset``),
letting the controller leave the rest untouched.
"""

from pydantic import BaseModel, ConfigDict


class RankingWeightsOut(BaseModel):
    """The doctor-locator ranking weights (core ``RankingWeightsValues``)."""

    model_config = ConfigDict(from_attributes=True)

    w_rating: float
    w_distance: float
    w_responsiveness: float
    w_verified: float
    w_recency: float


class RankingWeightsIn(BaseModel):
    """A partial update of the ranking weights — every field is optional.

    Only the weights the client actually sends are forwarded to the controller
    (via ``model_dump(exclude_unset=True)``); unset weights are left unchanged.
    """

    w_rating: float | None = None
    w_distance: float | None = None
    w_responsiveness: float | None = None
    w_verified: float | None = None
    w_recency: float | None = None


class FeatureFlagOut(BaseModel):
    """A single named feature flag (core ``FeatureFlagValue``)."""

    model_config = ConfigDict(from_attributes=True)

    key: str
    enabled: bool
    description: str | None = None


class FeatureFlagIn(BaseModel):
    """The desired state of a feature flag."""

    enabled: bool


class FeatureFlagsOut(BaseModel):
    """Every feature flag as a ``{key: enabled}`` mapping."""

    flags: dict[str, bool]
