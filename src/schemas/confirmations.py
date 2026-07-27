"""Request DTOs for the confirmation / waitlist surface."""

from datetime import datetime

from pydantic import BaseModel, Field
from sehaty.db import ConfirmationChannel


class ConfirmationSentIn(BaseModel):
    """The secretary recording that she sent the confirmation ask."""

    channel: ConfirmationChannel = Field(
        default=ConfirmationChannel.WHATSAPP_MANUAL,
        description="How it was sent; defaults to the manual wa.me flow.",
    )
    template: str | None = Field(
        default=None, description="Approved template name, for API sends only."
    )


class ConfirmationReplyIn(BaseModel):
    """The patient's answer, however it reached the cabinet."""

    confirmed: bool = Field(description="True if the patient is coming.")


class WaitlistJoinIn(BaseModel):
    """A patient asking to be told when a slot frees up."""

    doctor_id: int
    earliest_at: datetime | None = Field(
        default=None, description="Earliest date the patient can attend."
    )
    latest_at: datetime | None = Field(
        default=None, description="Past this date the entry stops being offered."
    )
    note: str | None = None
