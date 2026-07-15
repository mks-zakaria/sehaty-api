"""Doctor/assistant appointment-grid API tests over the in-memory SQLite fixture.

These routes are non-geo (the doctor-scoped booking grid + confirm-on-behalf), so
they run on the shared ``client``/``db`` fixtures without PostGIS — the conftest
builds the ``appointments`` + ``clinic_patients`` + ``availabilities`` +
``doctor_assistants`` tables. Flow under test: a patient books a slot on a
doctor's calendar; the doctor lists ``GET /doctor/appointments`` and sees the row
with a human-readable ``patient_name``; the doctor confirms it via
``POST /{id}/transition {status: CONFIRMED}``. An ASSISTANT linked to the doctor
does the same on the doctor's behalf (``?doctor_id=``): lists the grid and
confirms an appointment. An UNLINKED assistant and a PATIENT are both 403.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.assistants import AssistantController
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
            "email": f"grid-doc-{suffix}@clinic.ma",
            "password": "grid-pw-123",
            "full_name": f"Dr Grid {suffix}",
            "slug": f"dr-grid-{suffix}",
            "license_no": f"LIC-GRID-{suffix}",
            "phone": f"+21261500{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"grid-doc-{suffix}@clinic.ma", "password": "grid-pw-123"},
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


def _seed_unlinked_assistant(db: sessionmaker[Session], email: str) -> str:
    with db() as session:
        assistant = User(
            email=email,
            role=UserRole.ASSISTANT,
            is_active=True,
            password_hash="unused",
        )
        session.add(assistant)
        session.commit()
        assistant_id = int(assistant.id)
    return security.create_access_token(assistant_id, UserRole.ASSISTANT)


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


def test_doctor_lists_grid_and_confirms(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "1")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "grid-patient1@sehaty.ma")
    _book(client, patient_token, doctor_id)

    # The doctor sees the booked appointment with a human-readable patient name.
    listing = client.get("/api/v1/doctor/appointments", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["patient_name"] == "grid-patient1@sehaty.ma"
    assert row["status"] == "REQUESTED"
    assert row["reason"] == "Checkup"
    appointment_id = row["id"]

    # The doctor confirms it -> CONFIRMED.
    confirmed = client.post(
        f"/api/v1/doctor/appointments/{appointment_id}/transition",
        headers=_auth(doctor_token),
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"

    reread = client.get("/api/v1/doctor/appointments", headers=_auth(doctor_token))
    assert reread.json()[0]["status"] == "CONFIRMED"


def test_assistant_lists_grid_and_confirms_on_behalf(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "2")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "grid-patient2@sehaty.ma")
    _book(client, patient_token, doctor_id)

    # Onboard a linked assistant, then log them in (role ASSISTANT).
    AssistantController.create_assistant_account(
        doctor_id=doctor_id,
        email="grid-secretary@clinic.ma",
        password="sec-pw-123",
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "grid-secretary@clinic.ma", "password": "sec-pw-123"},
    )
    assert login.status_code == 200, login.text
    assistant_token = login.json()["access"]

    # The assistant lists the doctor's grid on their behalf (?doctor_id=).
    listing = client.get(
        "/api/v1/doctor/appointments",
        headers=_auth(assistant_token),
        params={"doctor_id": doctor_id},
    )
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["patient_name"] == "grid-patient2@sehaty.ma"
    appointment_id = rows[0]["id"]

    # The assistant confirms the appointment on the doctor's behalf.
    confirmed = client.post(
        f"/api/v1/doctor/appointments/{appointment_id}/transition",
        headers=_auth(assistant_token),
        params={"doctor_id": doctor_id},
        json={"status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"


def test_unlinked_assistant_and_patient_are_403(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, _doctor_token = _register_and_login_doctor(client, "3")
    unlinked_token = _seed_unlinked_assistant(db, "grid-unlinked@clinic.ma")
    _patient_id, patient_token = _seed_patient(db, "grid-patient3@sehaty.ma")

    # An assistant with no membership cannot act on the doctor's grid.
    unlinked = client.get(
        "/api/v1/doctor/appointments",
        headers=_auth(unlinked_token),
        params={"doctor_id": doctor_id},
    )
    assert unlinked.status_code == 403, unlinked.text

    # A patient is never allowed on the doctor grid.
    patient = client.get("/api/v1/doctor/appointments", headers=_auth(patient_token))
    assert patient.status_code == 403, patient.text
