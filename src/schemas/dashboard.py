"""Doctor dashboard DTOs — boundary translation over the core projections.

Maps ``DashboardController.doctor_stats``'s ``DoctorDashboard`` (and its nested
``NextAppointment``) into the JSON contract the doctor home consumes. No
business logic, no DB access.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NextAppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    start_at: datetime
    status: str
    patient_name: str


class DoctorDashboardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    today_total: int
    today_confirmed: int
    to_confirm: int
    upcoming_7d: int
    patients_total: int
    next_appointment: NextAppointmentOut | None = None
