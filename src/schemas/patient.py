"""Request/response DTOs for the patient-register surface — boundary only.

No business logic, no DB access. The ``*Out`` models translate the core
``PatientRegisterController`` frozen dataclass projections (``PatientRow``,
``PatientDetail``, ``VisitRow``) into the JSON contract clients consume; the
``*In`` models parse the request bodies. The register itself — doctor-scoped
listing with live-aggregated visit stats, walk-in creation and demographic
updates — lives in ``PatientRegisterController``.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PatientRowOut(BaseModel):
    """One patient-register grid row (the core ``PatientRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    tags: list[str] | None = None
    total_visits: int
    completed_visits: int
    no_show_count: int
    last_visit_at: datetime | None = None
    next_appointment_at: datetime | None = None
    created_at: datetime


class VisitOut(BaseModel):
    """One appointment in a patient's visit history (the core ``VisitRow``)."""

    model_config = ConfigDict(from_attributes=True)

    appointment_id: int
    start_at: datetime
    end_at: datetime
    status: str
    reason: str | None = None
    notes: str | None = None


class PatientDetailOut(BaseModel):
    """A register row with demographics + visit history (the core ``PatientDetail``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None = None
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    sex: str | None = None
    birth_year: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
    no_show_count: int
    total_visits: int
    created_at: datetime
    history: list[VisitOut]


class PatientCreateIn(BaseModel):
    """A walk-in / manually-entered patient (the ``POST /patients`` body)."""

    full_name: str
    phone: str | None = None
    email: str | None = None
    sex: str | None = None
    birth_year: int | None = None
    notes: str | None = None
    tags: list[str] | None = None


class PatientUpdateIn(BaseModel):
    """Demographic edits to a register row (the ``PATCH /patients/{id}`` body).

    Every field is optional; the router forwards only the ones the client sent
    (``model_dump(exclude_unset=True)``), so an omitted field is left untouched.
    """

    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    sex: str | None = None
    birth_year: int | None = None
    notes: str | None = None
    tags: list[str] | None = None
