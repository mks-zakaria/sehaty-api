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

import os
import subprocess
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from geoalchemy2 import Geography
from geoalchemy2 import functions as geo_functions
from sehaty.core.db import session as session_mod
from sehaty.db import (
    AdminConfig,
    Appointment,
    AuditLog,
    Availability,
    AvailabilityException,
    Cabinet,
    CabinetSession,
    ClinicPatient,
    CreditLedger,
    Diagnosis,
    Dispense,
    DispenseItem,
    DoctorAssistant,
    DoctorProfile,
    DoctorSpecialty,
    FeatureFlag,
    Invoice,
    Medication,
    Message,
    MessageThread,
    Notification,
    PatientProfile,
    Payment,
    PharmacyProduct,
    PharmacyStock,
    PhoneOtp,
    Plan,
    PracticeProfile,
    Prescription,
    PrescriptionItem,
    PrescriptionTemplate,
    RankingWeights,
    Referral,
    RefreshToken,
    ReputationScore,
    Review,
    Sale,
    SaleItem,
    Specialty,
    Subscription,
    TreatmentFeedback,
    User,
)
from sehaty.db.base import SehatyBase
from sqlalchemy import create_engine, text
from sqlalchemy import event as sa_event
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
    DoctorSpecialty.__table__,
    Specialty.__table__,
    AuditLog.__table__,
    Availability.__table__,
    AvailabilityException.__table__,
    Appointment.__table__,
    ClinicPatient.__table__,
    Cabinet.__table__,
    CabinetSession.__table__,
    DoctorAssistant.__table__,
    Review.__table__,
    ReputationScore.__table__,
    Plan.__table__,
    Subscription.__table__,
    Invoice.__table__,
    Payment.__table__,
    CreditLedger.__table__,
    Referral.__table__,
    AdminConfig.__table__,
    Notification.__table__,
    RankingWeights.__table__,
    FeatureFlag.__table__,
    PracticeProfile.__table__,
    Medication.__table__,
    Prescription.__table__,
    PrescriptionItem.__table__,
    PrescriptionTemplate.__table__,
    Dispense.__table__,
    DispenseItem.__table__,
    PharmacyStock.__table__,
    PharmacyProduct.__table__,
    Sale.__table__,
    SaleItem.__table__,
    Diagnosis.__table__,
    TreatmentFeedback.__table__,
    PatientProfile.__table__,
    MessageThread.__table__,
    Message.__table__,
]


@pytest.fixture
def db() -> Iterator[sessionmaker[Session]]:
    """In-memory SQLite session factory wired into `sehaty.core`."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa_event.listens_for(engine, "connect")
    def _register_geo_udfs(dbapi_conn: object, _record: object) -> None:
        # GeoAlchemy2 wraps geography reads in AsBinary(...); SQLite lacks it.
        # Test geopoints are NULL, so a no-op passthrough is enough for the
        # full-entity DoctorProfile loads (e.g. profile upsert).
        for _name in ("AsBinary", "ST_AsBinary", "ST_AsEWKB"):
            dbapi_conn.create_function(_name, 1, lambda v: v)  # type: ignore[attr-defined]

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


# --- PostGIS integration fixtures --------------------------------------------
# The doctor-profile round-trip (WKTElement writes + ST_X/ST_Y reads on the
# ``geopoint`` geography) cannot run on stock SQLite, so ``test_doctors_api.py``
# uses a live PostGIS reachable at ``DATABASE_URL`` (defaulting to the local
# Docker container) and SKIPs cleanly when none is available — mirroring
# sehaty-core's own ``pg_session`` fixture.
_DEFAULT_DATABASE_URL = "postgresql+psycopg://sehaty:sehaty@localhost:5432/sehaty"


def _database_url() -> str:
    return os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def _pg_engine():  # type: ignore[no-untyped-def]
    """Session-wide PostGIS engine; migrated once, or SKIP if unreachable."""
    url = _database_url()
    engine = create_engine(url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"PostGIS not reachable at {url}: {exc}")

    # Apply migrations once (idempotent). ``sehaty-migrate`` ships with the
    # sehaty-db dependency and reads DATABASE_URL itself.
    result = subprocess.run(
        ["sehaty-migrate"],
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # pragma: no cover - environment-dependent
        pytest.skip(f"sehaty-migrate failed:\n{result.stdout}\n{result.stderr}")

    yield engine
    engine.dispose()


@pytest.fixture
def pg_db(_pg_engine) -> Iterator[sessionmaker[Session]]:  # type: ignore[no-untyped-def]
    """PostGIS session factory wired into `sehaty.core`, blank per test.

    Truncates the user/doctor/specialty tables (CASCADE) before each test so the
    controllers — which open their own sessions via ``get_session()`` — see a
    clean slate.
    """
    factory = sessionmaker(bind=_pg_engine, expire_on_commit=False)
    with factory() as cleaner:
        cleaner.execute(text("TRUNCATE users, specialties RESTART IDENTITY CASCADE"))
        cleaner.commit()

    session_mod.set_session_factory(factory)
    yield factory
    session_mod.set_session_factory(None)


@pytest.fixture
def pg_client(pg_db: sessionmaker[Session]) -> Iterator[TestClient]:
    """TestClient bound to the app with the live PostGIS DB active."""
    with TestClient(app) as test_client:
        yield test_client
