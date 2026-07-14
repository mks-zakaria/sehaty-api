# sehaty-api

FastAPI **transport layer** for the Sehaty platform. Routers parse the request,
call **one** `sehaty-core` controller, and return. No SQLAlchemy queries live
here — that is `sehaty-core`'s job. The core `SehatyError` taxonomy is mapped
onto HTTP responses by a single exception handler in `src/main.py`.

## Architecture

```
Router (FastAPI)            src/routers/<domain>.py
  - parse path/query/body
  - call ONE controller method
  - serialize (schemas/) and return
        │
        ▼
Controller (sehaty-core)    validates, raises SehatyError, composes services
        │
        ▼
Service (sehaty-core)       the only layer with SQLAlchemy + sessions
```

The `SehatyError` taxonomy (`code` + `http_status`) is rendered as
`{"error": {"code": ..., "message": ...}}`.

## Layout

```
src/
  main.py            # app = FastAPI(...); CORS; SehatyError handler; health/ready; routers
  core_config.py     # pydantic-settings Settings (DATABASE_URL, JWT_SECRET, CORS, ...)
  _version.py        # __version__ — semantic-release rewrites this
  routers/
    doctors.py       # GET /api/v1/doctors
  schemas/
    doctors.py       # DoctorOut response DTO (boundary translation only)
tests/
  test_health.py     # /api/health smoke test, no DB required
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Liveness (no dependencies) |
| GET | `/api/ready` | Readiness |
| GET | `/api/v1/doctors` | Marketplace doctor search (`specialty`, `city`, `lat`, `lng`, `limit`) |
| GET | `/api/docs` | Swagger UI |
| GET | `/api/openapi.json` | OpenAPI schema |

## Develop

```bash
uv sync --all-extras                 # resolves sehaty-core + sehaty-db (editable path deps)
uv run ruff check . && uv run ruff format --check .
uv run pytest -q                     # health test, no live DB
uv run uvicorn main:app --app-dir src --reload
```

`sehaty-core` and `sehaty-db` are **local path dependencies**
(`[tool.uv.sources]`), so both must be checked out at `../sehaty-core` and
`../sehaty-db`. CI checks out `mks-zakaria/sehaty-core` and
`mks-zakaria/sehaty-db` alongside this repo before `uv sync`
(see `.github/workflows/primary.yml`).

## Conventions

Conventional Commits (enforced via pre-commit); versioning + tags via
`python-semantic-release` (`release.yml`). One PR = one issue.
