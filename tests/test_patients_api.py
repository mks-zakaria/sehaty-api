"""Patient-register API integration tests over the in-memory SQLite fixture.

These routes are non-geo (the doctor-scoped register grid), so they run on the
`client`/`db` fixtures without PostGIS — the shared conftest already builds the
``clinic_patients`` + ``appointments`` + ``availabilities`` tables. Flow under
test: a booking auto-creates a register row for the app-user patient; the doctor
lists their register and narrows it with ``?search=``; the doctor adds a walk-in
via ``POST`` and it appears in the list; ``GET /{id}`` returns detail + visit
history; ``PATCH`` updates notes/tags and a follow-up ``GET`` reflects it; and a
non-doctor (patient/admin) on the list is 403.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

# A fixed future date well clear of "today" so the slot always lands in range.
_TARGET_DAY: date = date.today() + timedelta(days=7)
_SLOT_START = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"pat-doc-{suffix}@clinic.ma",
            "password": "pat-pw-123",
            "full_name": f"Dr Register {suffix}",
            "slug": f"dr-register-{suffix}",
            "license_no": f"LIC-PAT-{suffix}",
            "phone": f"+21261300{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"pat-doc-{suffix}@clinic.ma", "password": "pat-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_patient(db: sessionmaker[Session], email: str) -> tuple[int, str]:
    with db() as session:
        patient = User(
            email=email,
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return patient_id, security.create_access_token(patient_id, UserRole.PATIENT)


def _seed_admin(db: sessionmaker[Session], email: str = "pat-admin@sehaty.ma") -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _add_window(client: TestClient, token: str) -> None:
    resp = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "12:00",
            "slot_minutes": 30,
        },
    )
    assert resp.status_code == 201, resp.text


def _book(client: TestClient, patient_token: str, doctor_id: int) -> None:
    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT_START.isoformat(), "reason": "Checkup"},
    )
    assert book.status_code == 201, book.text


def test_booking_creates_register_row_and_search_narrows(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "1")
    _add_window(client, doctor_token)
    patient_id, patient_token = _seed_patient(db, "reg-patient1@sehaty.ma")
    _book(client, patient_token, doctor_id)

    # The booking auto-created a register row (email backfilled from the User).
    listing = client.get("/api/v1/doctor/patients", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["user_id"] == patient_id
    assert rows[0]["email"] == "reg-patient1@sehaty.ma"
    assert rows[0]["total_visits"] == 1

    # ?search= narrows by email (case-insensitive contains).
    hit = client.get(
        "/api/v1/doctor/patients", headers=_auth(doctor_token), params={"search": "REG-Patient1"}
    )
    assert hit.status_code == 200, hit.text
    assert len(hit.json()) == 1
    miss = client.get(
        "/api/v1/doctor/patients", headers=_auth(doctor_token), params={"search": "zzz"}
    )
    assert miss.status_code == 200, miss.text
    assert miss.json() == []


def test_add_walkin_then_detail_and_update(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "2")

    # Add a walk-in via the endpoint -> 201, appears in the list.
    created = client.post(
        "/api/v1/doctor/patients",
        headers=_auth(doctor_token),
        json={"full_name": "Walk In Karim", "phone": "+212611223344", "tags": ["vip"]},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    patient_id = body["id"]
    assert body["user_id"] is None
    assert body["total_visits"] == 0

    listing = client.get("/api/v1/doctor/patients", headers=_auth(doctor_token))
    assert [r["id"] for r in listing.json()] == [patient_id]

    # GET /{id} returns detail + (empty) history.
    detail = client.get(f"/api/v1/doctor/patients/{patient_id}", headers=_auth(doctor_token))
    assert detail.status_code == 200, detail.text
    assert detail.json()["full_name"] == "Walk In Karim"
    assert detail.json()["history"] == []

    # PATCH updates notes/tags; a follow-up GET reflects it.
    patched = client.patch(
        f"/api/v1/doctor/patients/{patient_id}",
        headers=_auth(doctor_token),
        json={"notes": "Allergic to penicillin", "tags": ["vip", "allergy"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["notes"] == "Allergic to penicillin"
    assert patched.json()["tags"] == ["vip", "allergy"]

    reread = client.get(f"/api/v1/doctor/patients/{patient_id}", headers=_auth(doctor_token))
    assert reread.json()["notes"] == "Allergic to penicillin"
    assert reread.json()["tags"] == ["vip", "allergy"]


def test_unknown_patient_is_404(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "3")
    resp = client.get("/api/v1/doctor/patients/9999", headers=_auth(doctor_token))
    assert resp.status_code == 404, resp.text


def test_non_doctor_cannot_list_register(client: TestClient, db: sessionmaker[Session]) -> None:
    _, patient_token = _seed_patient(db, "reg-patient2@sehaty.ma")
    admin_token = _seed_admin(db)
    for token in (patient_token, admin_token):
        resp = client.get("/api/v1/doctor/patients", headers=_auth(token))
        assert resp.status_code == 403, resp.text
