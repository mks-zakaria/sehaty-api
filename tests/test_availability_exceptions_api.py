"""Availability-exception + doctor-timezone API tests over in-memory SQLite.

These exercise the DOCTOR-scoped exception endpoints (BLOCK/OPEN a date) and the
timezone additions to the profile PUT + public read. They reuse the shared
``client``/``db`` fixtures (SQLite via ``set_session_factory``); ``conftest``
already registers the geo shims and includes ``availability_exceptions`` in the
created tables.

The public read (``GET /{slug}``) goes through ``DoctorController.get_by_slug``,
which projects the PostGIS ``geopoint`` through ``ST_X``/``ST_Y`` — functions
stock SQLite lacks — so we register dialect-scoped shims that resolve them to
``NULL`` (these tests never set coordinates, so the round-trip is irrelevant;
only ``timezone`` is asserted).
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from geoalchemy2 import functions as geo_functions
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker


@compiles(geo_functions.ST_X, "sqlite")
def _st_x_null_on_sqlite(element, compiler, **kw) -> str:
    # SQLite has no PostGIS accessor; coordinates are irrelevant here.
    return "NULL"


@compiles(geo_functions.ST_Y, "sqlite")
def _st_y_null_on_sqlite(element, compiler, **kw) -> str:
    return "NULL"


@compiles(geo_functions.ST_AsEWKB, "sqlite")
def _as_ewkb_passthrough_on_sqlite(element, compiler, **kw) -> str:
    # A full-entity DoctorProfile load wraps geopoint in a WKB reader SQLite
    # lacks; read the raw (always-NULL in these tests) column instead.
    return compiler.process(next(iter(element.clauses)), **kw)


@compiles(geo_functions.ST_AsBinary, "sqlite")
def _as_binary_passthrough_on_sqlite(element, compiler, **kw) -> str:
    return compiler.process(next(iter(element.clauses)), **kw)


_TARGET_DAY: date = date.today() + timedelta(days=10)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"exc-doc-{suffix}@clinic.ma",
            "password": "exc-pw-123",
            "full_name": f"Dr Exc {suffix}",
            "slug": f"dr-exc-{suffix}",
            "license_no": f"LIC-EXC-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"exc-doc-{suffix}@clinic.ma", "password": "exc-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_admin_token(db: sessionmaker[Session], tag: str) -> str:
    with db() as session:
        admin = User(
            email=f"exc-admin-{tag}@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        return security.create_access_token(int(admin.id), UserRole.ADMIN)


def test_block_exception_create_list_delete(client: TestClient, db: sessionmaker[Session]) -> None:
    _, token = _register_doctor(client, "1")
    day = _TARGET_DAY.isoformat()

    # POST a whole-day BLOCK.
    created = client.post(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(token),
        json={"date": day, "kind": "BLOCK", "reason": "conference"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    exc_id = body["id"]
    assert body["kind"] == "BLOCK"
    assert body["date"] == day
    assert body["reason"] == "conference"
    assert body["start_time"] is None and body["end_time"] is None

    # GET lists it.
    listed = client.get(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(token),
    )
    assert listed.status_code == 200, listed.text
    assert [e["id"] for e in listed.json()] == [exc_id]

    # DELETE removes it.
    deleted = client.delete(
        f"/api/v1/doctors/me/availability/exceptions/{exc_id}",
        headers=_auth(token),
    )
    assert deleted.status_code == 204, deleted.text
    again = client.get(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(token),
    )
    assert again.json() == []


def test_open_exception_valid_and_invalid(client: TestClient, db: sessionmaker[Session]) -> None:
    _, token = _register_doctor(client, "2")
    day = _TARGET_DAY.isoformat()

    # A valid OPEN window with start/end/slot_minutes.
    ok = client.post(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(token),
        json={
            "date": day,
            "kind": "OPEN",
            "start_time": "09:00",
            "end_time": "12:00",
            "slot_minutes": 30,
        },
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "OPEN"
    assert ok.json()["slot_minutes"] == 30

    # An OPEN without times is a controller validation error -> 400/422.
    bad = client.post(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(token),
        json={"date": day, "kind": "OPEN"},
    )
    assert bad.status_code in (400, 422), bad.text


def test_non_doctor_cannot_manage_exceptions(client: TestClient, db: sessionmaker[Session]) -> None:
    admin_token = _seed_admin_token(db, "1")
    resp = client.get(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 403, resp.text
    post = client.post(
        "/api/v1/doctors/me/availability/exceptions",
        headers=_auth(admin_token),
        json={"date": _TARGET_DAY.isoformat(), "kind": "BLOCK"},
    )
    assert post.status_code == 403, post.text


def test_profile_timezone_persists_and_reads_back(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, token = _register_doctor(client, "3")

    put = client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(token),
        json={"full_name": "Dr Exc 3", "timezone": "Europe/Paris"},
    )
    assert put.status_code == 200, put.text
    slug = put.json()["slug"]

    # Accredit so the public page resolves.
    admin_token = _seed_admin_token(db, "2")
    accredit = client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers=_auth(admin_token),
    )
    assert accredit.status_code == 200, accredit.text

    page = client.get(f"/api/v1/doctors/{slug}")
    assert page.status_code == 200, page.text
    assert page.json()["timezone"] == "Europe/Paris"


def test_profile_invalid_timezone_rejected(client: TestClient, db: sessionmaker[Session]) -> None:
    _, token = _register_doctor(client, "4")
    resp = client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(token),
        json={"full_name": "Dr Exc 4", "timezone": "Mars/Phobos"},
    )
    assert resp.status_code in (400, 422), resp.text
