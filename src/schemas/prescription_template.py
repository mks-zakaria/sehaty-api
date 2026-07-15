"""Request/response DTOs for a doctor's reusable prescription templates.

No business logic, no DB access. ``*In`` models parse request bodies; the
``*Out`` models translate the ``sehaty.core``
:class:`~sehaty.core.controllers.prescription_templates.PrescriptionTemplateController`
frozen dataclass projections (``TemplateRow`` / ``TemplateItem``) into the JSON
contract clients consume. A template is a doctor's named, reusable preset that
pre-builds a common freehand prescription so it can be dropped into a new one in
one click.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TemplateItemIn(BaseModel):
    """One freehand medication row of a new template."""

    drug_name: str
    dosage: str
    frequency: str
    duration_days: int | None = None
    instructions: str | None = None


class TemplateItemOut(BaseModel):
    """One resolved template row (the core ``TemplateItem``)."""

    model_config = ConfigDict(from_attributes=True)

    drug_name: str
    dosage: str
    frequency: str
    duration_days: int | None = None
    instructions: str | None = None


class TemplateCreateIn(BaseModel):
    """A new prescription template (the ``POST .../prescription-templates`` body)."""

    name: str
    notes: str | None = None
    items: list[TemplateItemIn]


class TemplateOut(BaseModel):
    """A prescription template as seen on the wire (the core ``TemplateRow``)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    notes: str | None = None
    items: list[TemplateItemOut]
    created_at: datetime
