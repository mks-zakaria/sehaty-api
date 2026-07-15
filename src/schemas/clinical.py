"""Request/response DTOs for the clinical workspace — boundary translation only.

No business logic, no DB access. ``*In`` models parse request bodies; the
``*Out`` models translate the ``sehaty.core`` clinical controllers' frozen
dataclass projections (``PracticeProfileRow``, ``PrescriptionDetail`` /
``PrescriptionSummary`` / ``PrescriptionItemRow``, ``DiagnosisRow``,
``FeedbackRow``) into the JSON contract clients consume. The printable
prescription document maps cleanly: :class:`PrescriptionDetailOut` nests the
``letterhead`` (a :class:`PracticeProfileOut`) and the ``items`` list
(:class:`PrescriptionItemOut`). Practice-profile letterheads, prescriptions,
diagnoses and patient treatment-feedback all live in their controllers.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

# --- Practice profiles (letterheads) -----------------------------------------


class PracticeProfileOut(BaseModel):
    """A doctor's letterhead as seen on the wire (the core ``PracticeProfileRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    doctor_id: int
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
    is_default: bool
    created_at: datetime


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


class PrescriptionItemOut(BaseModel):
    """One resolved prescription line (the core ``PrescriptionItemRow``)."""

    model_config = ConfigDict(from_attributes=True)

    drug_name: str | None = None
    dosage: str
    frequency: str
    duration_days: int | None = None
    quantity: int
    instructions: str | None = None


class PrescriptionCreateIn(BaseModel):
    """A new prescription for a register patient (the ``POST .../prescriptions`` body)."""

    items: list[PrescriptionItemIn]
    practice_profile_id: int | None = None
    appointment_id: int | None = None
    notes: str | None = None
    expires_days: int | None = None


class PrescriptionSummaryOut(BaseModel):
    """A prescription list row (the core ``PrescriptionSummary``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    status: str
    issued_at: datetime
    expires_at: datetime
    item_count: int


class PrescriptionDetailOut(BaseModel):
    """A prescription with its items + letterhead (the core ``PrescriptionDetail``).

    ``letterhead`` is the practice-profile snapshot needed to render the
    printable document (``None`` when never set / since removed); ``items`` is
    the resolved drug list.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    status: str
    issued_at: datetime
    expires_at: datetime
    notes: str | None = None
    practice_profile_id: int | None = None
    items: list[PrescriptionItemOut]
    letterhead: PracticeProfileOut | None = None


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


class DiagnosisOut(BaseModel):
    """A diagnosis as seen on the wire (the core ``DiagnosisRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    icd10: str | None = None
    notes: str | None = None
    diagnosed_at: datetime
    appointment_id: int | None = None


# --- Treatment feedback ------------------------------------------------------


class FeedbackIn(BaseModel):
    """A patient's outcome on one of their own records (the ``POST /me/feedback`` body)."""

    target_type: str
    target_id: int
    outcome: str
    comment: str | None = None


class FeedbackOut(BaseModel):
    """A treatment-feedback entry as seen on the wire (the core ``FeedbackRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    target_type: str
    target_id: int
    outcome: str
    comment: str | None = None
    author_user_id: int | None = None
    created_at: datetime
