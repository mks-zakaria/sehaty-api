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
from routers.auth import router as auth_router
from routers.doctors import router as doctors_router

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
