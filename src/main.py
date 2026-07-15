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
from routers.appointments import router as appointments_router
from routers.auth import router as auth_router
from routers.availability import router as availability_router
from routers.billing import router as billing_router
from routers.config import router as config_router
from routers.diagnoses import router as diagnoses_router
from routers.doctors import router as doctors_router
from routers.feedback import router as feedback_router
from routers.notifications import router as notifications_router
from routers.patients import router as patients_router
from routers.practice import router as practice_router
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
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
app.include_router(reviews_router)
app.include_router(admin_router)
app.include_router(billing_router)
app.include_router(referrals_router)
app.include_router(patients_router)
app.include_router(notifications_router)
app.include_router(reports_router)
app.include_router(config_router)
app.include_router(practice_router)
app.include_router(prescriptions_router)
app.include_router(diagnoses_router)
app.include_router(feedback_router)
