"""Shared test fixtures for the API suite.

Auth flows touch the DB, so we inject an in-memory SQLite session factory via
`sehaty.core`'s `set_session_factory`. The PostGIS ``Geography`` column + GIST
index on ``DoctorProfile`` are not buildable on stock SQLite, so we register
dialect-scoped compilation shims (geo type -> ``TEXT``; ``ST_GeogFromText`` ->
pass-through) purely for the test engine — this mirrors sehaty-core's own
`tests/test_auth.py` and lets `register_doctor` run without PostGIS.

`test_health.py` never requests the `db`/`client` fixtures, so it still runs
without a database.
"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from geoalchemy2 import Geography
from geoalchemy2 import functions as geo_functions
from sehaty.core.db import session as session_mod
from sehaty.db import AuditLog, DoctorProfile, PhoneOtp, RefreshToken, User
from sehaty.db.base import SehatyBase
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from main import app


@compiles(Geography, "sqlite")
def _geography_as_text_on_sqlite(element, compiler, **kw) -> str:
    # SQLite has no geography type; store the column as opaque TEXT for tests.
    return "TEXT"


@compiles(geo_functions.ST_GeogFromText, "sqlite")
def _geog_bind_passthrough_on_sqlite(element, compiler, **kw) -> str:
    # Skip the PostGIS constructor SQLite lacks; bind the raw value instead.
    return compiler.process(list(element.clauses)[0], **kw)


_TABLES = [
    User.__table__,
    RefreshToken.__table__,
    PhoneOtp.__table__,
    DoctorProfile.__table__,
    AuditLog.__table__,
]


@pytest.fixture
def db() -> Iterator[sessionmaker[Session]]:
    """In-memory SQLite session factory wired into `sehaty.core`."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SehatyBase.metadata.create_all(engine, tables=_TABLES)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session_mod.set_session_factory(factory)
    yield factory
    session_mod.set_session_factory(None)


@pytest.fixture
def client(db: sessionmaker[Session]) -> Iterator[TestClient]:
    """TestClient bound to the app with the in-memory DB active."""
    with TestClient(app) as test_client:
        yield test_client
