"""Request DTOs for the clinical workspace — inbound boundary translation only.

No business logic, no DB access. ``*In`` models parse request bodies. Responses
are the ``sehaty.core`` clinical controllers' own projections
(``PracticeProfileRow``, ``PrescriptionDetail`` / ``PrescriptionSummary`` /
``PrescriptionItemRow``, ``DiagnosisRow``, ``FeedbackRow``), returned directly by
the routers as their ``response_model``. Practice-profile letterheads,
prescriptions, diagnoses and patient treatment-feedback all live in their
controllers.
"""

from datetime import datetime

from pydantic import BaseModel

# --- Practice profiles (letterheads) -----------------------------------------


class PracticeProfileIn(BaseModel):
    """A new letterhead (the ``POST /doctor/practice-profiles`` body)."""

    name: str
    clinic_name: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    header_line: str | None = None
    signature_name: str | None = None
    signature_image_url: str | None = None
    watermark_text: str | None = None
    watermark_image_url: str | None = None
    is_default: bool = False


class PracticeProfileUpdateIn(BaseModel):
    """Edits to a letterhead (the ``PATCH /doctor/practice-profiles/{id}`` body).

    Every field is optional; the router forwards only the ones the client sent
    (``model_dump(exclude_unset=True)``), so an omitted field is left untouched.
    """

    name: str | None = None
    clinic_name: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    header_line: str | None = None
    signature_name: str | None = None
    signature_image_url: str | None = None
    watermark_text: str | None = None
    watermark_image_url: str | None = None
    is_default: bool | None = None


# --- Prescriptions -----------------------------------------------------------


class PrescriptionItemIn(BaseModel):
    """One line of a new prescription (catalog-linked OR freehand)."""

    drug_name: str | None = None
    medication_id: int | None = None
    dosage: str
    frequency: str
    duration_days: int | None = None
    quantity: int | None = None
    instructions: str | None = None


class PrescriptionCreateIn(BaseModel):
    """A new prescription for a register patient (the ``POST .../prescriptions`` body)."""

    items: list[PrescriptionItemIn]
    practice_profile_id: int | None = None
    appointment_id: int | None = None
    notes: str | None = None
    expires_days: int | None = None


# --- Diagnoses ---------------------------------------------------------------


class DiagnosisCreateIn(BaseModel):
    """A new diagnosis for a register patient (the ``POST .../diagnoses`` body)."""

    label: str
    icd10: str | None = None
    notes: str | None = None
    appointment_id: int | None = None
    diagnosed_at: datetime | None = None


class DiagnosisUpdateIn(BaseModel):
    """Edits to a diagnosis (the ``PATCH /doctor/diagnoses/{id}`` body).

    Every field is optional; the router forwards only the ones the client sent
    (``model_dump(exclude_unset=True)``).
    """

    label: str | None = None
    icd10: str | None = None
    notes: str | None = None
    appointment_id: int | None = None
    diagnosed_at: datetime | None = None


# --- Treatment feedback ------------------------------------------------------


class FeedbackIn(BaseModel):
    """A patient's outcome on one of their own records (the ``POST /me/feedback`` body)."""

    target_type: str
    target_id: int
    outcome: str
    comment: str | None = None
