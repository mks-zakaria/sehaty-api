"""Inbound request DTOs for the cabinet + consultation surface.

No business logic, no DB access — just the request bodies. Responses are served
directly from the core projections (``CabinetRow`` / ``CabinetSessionRow`` /
``AppointmentRow`` / ``ConsultationRow`` / ``WaitingPatientRow``).
"""

from pydantic import BaseModel


class CabinetIn(BaseModel):
    """Create a cabinet (owned by the calling doctor)."""

    name: str
    address: str | None = None


class OpenSessionIn(BaseModel):
    """Open a shift. ``acting_doctor_id`` defaults to the caller (owner working
    their own cabinet); set it to a colleague's user id when a substitute covers."""

    acting_doctor_id: int | None = None


class CheckInIn(BaseModel):
    """Secretary checks a patient in against an open cabinet session."""

    cabinet_session_id: int


class WaitingCountIn(BaseModel):
    """Secretary sets how many people are in the waiting room right now."""

    count: int


class AlertThresholdIn(BaseModel):
    """Doctor sets the waiting-room alert threshold (null disables the alert)."""

    threshold: int | None = None


class CompleteConsultationIn(BaseModel):
    """The structured consultation record the doctor saves on completion."""

    chief_complaint: str | None = None
    symptoms: dict | None = None
    vitals: dict | None = None
    exam_notes: str | None = None
