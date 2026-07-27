"""Slug-keyed public slots endpoint tests over the in-memory SQLite fixture.

``GET /api/v1/doctors/{slug}/slots`` is non-geo — ``get_public_slots`` projects
only ``user_id``/``verification_status`` and expands availability — so it runs on
the ``client``/``db`` fixtures without PostGIS. Two behaviours are pinned: a
VERIFIED doctor with a window returns the expanded slots; a PENDING slug 404s
(unverified profiles are never leaked), matching ``GET /{slug}``.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

# A fixed future date well clear of "today" so the slot always lands in range.
_TARGET_DAY: date = date.today() + timedelta(days=8)
_SLOT_START = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_doctor(client: TestClient, suffix: str, slug: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"slug-doc-{suffix}@clinic.ma",
            "password": "slug-pw-123",
            "full_name": f"Dr Slug {suffix}",
            "slug": slug,
            "license_no": f"LIC-SLUG-{suffix}",
            "phone": f"+21261300{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"slug-doc-{suffix}@clinic.ma", "password": "slug-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _accredit(client: TestClient, db: sessionmaker[Session], doctor_id: int) -> None:
    with db() as session:
        admin = User(
            email=f"slug-admin-{doctor_id}@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_token = security.create_access_token(int(admin.id), UserRole.ADMIN)
    resp = client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text


def test_slug_slots_verified_returns_slots(
    client: TestClient, db: sessionmaker[Session], plans
) -> None:
    doctor_id, doctor_token = _register_doctor(client, "1", "dr-slug-one")
    _accredit(client, db, doctor_id)

    add = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(doctor_token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "12:00",
            "slot_minutes": 30,
        },
    )
    assert add.status_code == 201, add.text

    resp = client.get(
        "/api/v1/doctors/dr-slug-one/slots",
        params={"from": _TARGET_DAY.isoformat(), "to": _TARGET_DAY.isoformat()},
    )
    assert resp.status_code == 200, resp.text
    starts = {datetime.fromisoformat(s["start_at"]) for s in resp.json()}
    assert len(resp.json()) == 6  # 09:00..11:30, 30-minute steps
    assert _SLOT_START in starts


def test_slug_slots_pending_doctor_is_404(client: TestClient, db: sessionmaker[Session]) -> None:
    # Registered but never accredited -> PENDING -> the slug is not resolvable.
    _register_doctor(client, "2", "dr-slug-two")
    resp = client.get(
        "/api/v1/doctors/dr-slug-two/slots",
        params={"from": _TARGET_DAY.isoformat(), "to": _TARGET_DAY.isoformat()},
    )
    assert resp.status_code == 404, resp.text


def test_slug_slots_unknown_slug_is_404(client: TestClient, db: sessionmaker[Session]) -> None:
    resp = client.get(
        "/api/v1/doctors/no-such-doctor/slots",
        params={"from": _TARGET_DAY.isoformat(), "to": _TARGET_DAY.isoformat()},
    )
    assert resp.status_code == 404, resp.text
