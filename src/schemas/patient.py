"""Request DTOs for the patient-register surface — boundary only.

No business logic, no DB access. The ``*In`` models parse the request bodies;
responses are served directly from the core ``PatientRegisterController``
projections (``PatientRow``, ``PatientDetail``, ``VisitRow``), which are pydantic
models used as FastAPI ``response_model`` without a parallel ``*Out`` mirror. The
register itself — doctor-scoped listing with live-aggregated visit stats, walk-in
creation and demographic updates — lives in ``PatientRegisterController``.
"""

from pydantic import BaseModel


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
