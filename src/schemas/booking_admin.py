"""Admin DTO for the per-doctor booking switch."""

from pydantic import BaseModel, Field


class BookingToggleIn(BaseModel):
    """Open or close one doctor's agenda."""

    enabled: bool = Field(
        description=(
            "True opens the agenda and starts the free trial if they have never "
            "subscribed; false closes it regardless of billing."
        )
    )
