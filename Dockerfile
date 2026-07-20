# syntax=docker/dockerfile:1
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PORT=8000

WORKDIR /code

# psycopg[binary] ships its own libpq wheels; only the runtime shared lib is
# needed for the geo/db stack pulled in transitively.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpq5 \
 && rm -rf /var/lib/apt/lists/*

# uv must be recent enough to parse the lockfile format (uv.lock revision 3);
# pin to the version that writes it. Bump in lockstep with the local uv.
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /uvx /usr/local/bin/

# Deps first (cache survives source edits).
#
# NOTE: sehaty-core and sehaty-db are local path deps ([tool.uv.sources]:
# ../sehaty-core, ../sehaty-db). To resolve them, build with the *parent*
# `sehaty/` directory as the build context so the siblings are visible, e.g.:
#   docker build -f sehaty-api/Dockerfile -t sehaty-api .
# and copy the siblings in before syncing. The long-term cleaner path is to
# publish sehaty-core/sehaty-db as wheels and `uv add` them (see delivery.md).
COPY sehaty-core/ /sehaty-core/
COPY sehaty-db/ /sehaty-db/
COPY sehaty-api/pyproject.toml sehaty-api/uv.lock /code/
RUN uv sync --frozen --no-install-project --no-dev

# Copy source last.
COPY sehaty-api/src/ /code/src/
COPY sehaty-api/docker-entrypoint.sh /code/docker-entrypoint.sh
RUN chmod +x /code/docker-entrypoint.sh

HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=12 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/api/health').status < 500 else 1)"

CMD ["sh", "-c", "uvicorn main:app --app-dir src --host 0.0.0.0 --port ${PORT:-8000}"]
