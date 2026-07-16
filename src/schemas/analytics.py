"""Doctor analytics DTOs — boundary translation over the core projections.

Maps ``DoctorAnalyticsController.doctor_analytics``'s ``DoctorAnalytics`` (and
its nested ``MonthStat`` / ``MonthCount``) into the JSON contract the doctor
practice-insights page consumes. No business logic, no DB access.
"""

from pydantic import BaseModel, ConfigDict


class MonthStatOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    total: int
    completed: int
    no_show: int
    cancelled: int
    estimated_revenue: float


class MonthCountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    count: int


class DoctorAnalyticsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    by_month: list[MonthStatOut]
    no_show_rate: float
    total_appointments: int
    total_completed: int
    total_no_show: int
    avg_rating: float
    review_count: int
    reviews_by_month: list[MonthCountOut]
