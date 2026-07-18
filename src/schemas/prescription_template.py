"""Request DTOs for a doctor's reusable prescription templates.

No business logic, no DB access. ``*In`` models parse request bodies. Responses
are served directly from the ``sehaty.core``
:class:`~sehaty.core.controllers.prescription_templates.PrescriptionTemplateController`
projections (``TemplateRow`` / ``TemplateItem``), which the router uses as its
``response_model``. A template is a doctor's named, reusable preset that
pre-builds a common freehand prescription so it can be dropped into a new one in
one click.
"""

from pydantic import BaseModel


class TemplateItemIn(BaseModel):
    """One freehand medication row of a new template."""

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
