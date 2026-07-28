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

## Operator scripts

Run from `sehaty-api/`. The first two need `DATABASE_URL`; the print tools need
the optional `print` extra (`reportlab` + `segno`), kept out of the runtime
dependencies so the API image carries no PDF engine.

| Script | What it does |
| --- | --- |
| `scripts/seed_demo.py` | Wipe and reseed a full Casablanca demo dataset. |
| `scripts/import_doctors.py` | CSV → published, unclaimed doctor pages. Idempotent; never republishes a doctor who requested removal, never overwrites a claimed profile. `--dry-run` validates without writing. |
| `scripts/print_assets.py` | A5 waiting-room plaques + A4 sheets of 10 pocket QR cards. Reads the database, or `--csv` for the same file the importer takes. |
| `scripts/sales_sheet.py` | The Pack Présence one-pager (A4 recto/verso, French). |

```bash
uv run python scripts/import_doctors.py scripts/doctors.sample.csv --dry-run

# Print assets need the domain the QR will encode. There is no default: a
# plaque on a waiting-room wall cannot be corrected, only reprinted, and the
# final domain is not settled yet.
SEHATY_SITE_URL=https://sehaty-landing.vercel.app \
  uv run --extra print python scripts/print_assets.py \
  --csv scripts/doctors.sample.csv --out ./print --draft   # watermarked preview

uv run --extra print python scripts/sales_sheet.py --out ./print
```

`--draft` stamps every page "NE PAS IMPRIMER" and is the only way to generate
against a preview host. Drop it, and set `SEHATY_SITE_URL` to the real domain,
once that is confirmed.

QR codes are drawn as vector rectangles rather than embedded bitmaps, and every
one carries `?src=qr` so scans are attributable in the landing analytics. The
printed text is French only — reportlab cannot shape Arabic, and rendering it
unshaped would print disconnected, reversed letters.

## Conventions

Conventional Commits (enforced via pre-commit); versioning + tags via
`python-semantic-release` (`release.yml`). One PR = one issue.
