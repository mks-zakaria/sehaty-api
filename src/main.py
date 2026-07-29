"""Sehaty API — FastAPI transport layer.

Entry point run as `uvicorn main:app --app-dir src`, so imports are top-level
(`from routers.doctors import ...`), not `src.routers...`. Routers parse and
delegate to a single `sehaty.core` controller; this module maps the core
`SehatyError` taxonomy onto HTTP responses.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sehaty.core.errors import SehatyError

from core_config import settings
from routers.admin import router as admin_router
from routers.analytics import router as analytics_router
from routers.appointments import router as appointments_router
from routers.articles import router as articles_router
from routers.assistants import router as assistants_router
from routers.auth import router as auth_router
from routers.availability import router as availability_router
from routers.billing import router as billing_router
from routers.cabinets import router as cabinets_router
from routers.chatbot import router as chatbot_router
from routers.cities import router as cities_router
from routers.claims import router as claims_router
from routers.clinic_messages import router as clinic_messages_router
from routers.config import router as config_router
from routers.confirmations import router as confirmations_router
from routers.consultations import router as consultations_router
from routers.dashboard import router as dashboard_router
from routers.diagnoses import router as diagnoses_router
from routers.doctor_appointments import router as doctor_appointments_router
from routers.doctors import router as doctors_router
from routers.export import router as export_router
from routers.feedback import router as feedback_router
from routers.landing_config import router as landing_config_router
from routers.landing_events import router as landing_events_router
from routers.messages import router as messages_router
from routers.notifications import router as notifications_router
from routers.onboarding import router as onboarding_router
from routers.patient_ledger import me_router as patient_ledger_me_router
from routers.patient_ledger import router as patient_ledger_router
from routers.patients import router as patients_router
from routers.pharmacy import router as pharmacy_router
from routers.practice import router as practice_router
from routers.prescription_templates import router as prescription_templates_router
from routers.prescriptions import router as prescriptions_router
from routers.referrals import router as referrals_router
from routers.reports import router as reports_router
from routers.reviews import router as reviews_router
from routers.specialties import router as specialties_router

app = FastAPI(
    title="Sehaty API",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

# A wildcard origin and credentialled requests are mutually exclusive: a browser
# rejects `Access-Control-Allow-Origin: *` on any request carrying credentials,
# so the permissive dev default has to drop credentials to work at all.
_allows_any = settings.cors_allows_any
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # The regex catches this team's Vercel deployments, whose hostnames change
    # on every deploy and cannot be enumerated ahead of time.
    allow_origin_regex=None if _allows_any else (settings.cors_origin_regex or None),
    allow_credentials=not _allows_any,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SehatyError)
async def sehaty_error_handler(_request: Request, exc: SehatyError) -> JSONResponse:
    """Map the core business-error taxonomy onto HTTP responses."""
    return JSONResponse(
        {"error": {"code": exc.code, "message": str(exc)}},
        status_code=exc.http_status,
    )


@app.get("/api/health")
def health() -> dict[str, str]:
    """Liveness probe — no dependencies, must answer without a DB."""
    return {"status": "ok"}


@app.get("/api/ready")
def ready() -> dict[str, str]:
    """Readiness probe. Kept dependency-free for now; deepen when needed."""
    return {"status": "ready"}


app.include_router(auth_router)
app.include_router(doctors_router)
app.include_router(availability_router)
app.include_router(appointments_router)
app.include_router(specialties_router)
app.include_router(cities_router)
app.include_router(articles_router)
app.include_router(onboarding_router)
app.include_router(chatbot_router)
app.include_router(claims_router)
app.include_router(confirmations_router)
app.include_router(landing_events_router)
app.include_router(landing_config_router)
app.include_router(reviews_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(referrals_router)
app.include_router(patients_router)
app.include_router(patient_ledger_router)
app.include_router(patient_ledger_me_router)
app.include_router(dashboard_router)
app.include_router(analytics_router)
app.include_router(notifications_router)
app.include_router(reports_router)
app.include_router(config_router)
app.include_router(practice_router)
app.include_router(prescriptions_router)
app.include_router(prescription_templates_router)
app.include_router(diagnoses_router)
app.include_router(feedback_router)
app.include_router(assistants_router)
app.include_router(doctor_appointments_router)
app.include_router(messages_router)
app.include_router(clinic_messages_router)
app.include_router(cabinets_router)
app.include_router(consultations_router)
app.include_router(export_router)
app.include_router(pharmacy_router)
