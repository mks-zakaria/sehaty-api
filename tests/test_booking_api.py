"""Booking API integration tests over the in-memory SQLite fixture.

These routes are non-geo (availability, slots, appointments), so they run on the
`client`/`db` fixtures without PostGIS. Flow under test: a doctor adds a weekly
availability window; the public slots endpoint expands it; a patient books a
free slot (201), a double-book is rejected (409); the patient lists their
appointment; the doctor confirms then completes; the patient cancels a second
booking; and a non-doctor adding availability is 403.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

# A fixed future date well clear of "today" so the slot always lands in range.
_TARGET_DAY: date = date.today() + timedelta(days=7)
_SLOT_START = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)
_SECOND_SLOT_START = _SLOT_START + timedelta(minutes=30)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"book-doc-{suffix}@clinic.ma",
            "password": "book-pw-123",
            "full_name": f"Dr Book {suffix}",
            "slug": f"dr-book-{suffix}",
            "license_no": f"LIC-BOOK-{suffix}",
            "phone": f"+21261200{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"book-doc-{suffix}@clinic.ma", "password": "book-pw-123"},
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


def test_booking_end_to_end(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "1")

    # Doctor adds a weekly availability window; it is listed back.
    _add_window(client, doctor_token)
    listing = client.get("/api/v1/doctors/me/availability", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1
    assert listing.json()[0]["weekday"] == _TARGET_DAY.weekday()

    # Public slots endpoint expands the window into concrete slots.
    slots_resp = client.get(
        f"/api/v1/doctors/{doctor_id}/slots",
        params={"from": _TARGET_DAY.isoformat(), "to": _TARGET_DAY.isoformat()},
    )
    assert slots_resp.status_code == 200, slots_resp.text
    starts = {datetime.fromisoformat(s["start_at"]) for s in slots_resp.json()}
    assert len(slots_resp.json()) == 6  # 09:00..11:30, 30-minute steps
    assert _SLOT_START in starts

    # Patient books the first slot -> 201.
    patient_id, patient_token = _seed_patient(db, "book-patient1@sehaty.ma")
    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={
            "doctor_id": doctor_id,
            "start_at": _SLOT_START.isoformat(),
            "reason": "Checkup",
        },
    )
    assert book.status_code == 201, book.text
    appt = book.json()
    assert appt["status"] == "REQUESTED"
    assert appt["patient_id"] == patient_id
    appt_id = appt["id"]

    # Double-booking the same slot -> 409.
    dup = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT_START.isoformat()},
    )
    assert dup.status_code == 409, dup.text

    # The booked slot no longer appears in the public listing.
    slots_after = client.get(
        f"/api/v1/doctors/{doctor_id}/slots",
        params={"from": _TARGET_DAY.isoformat(), "to": _TARGET_DAY.isoformat()},
    )
    assert _SLOT_START not in {datetime.fromisoformat(s["start_at"]) for s in slots_after.json()}

    # Patient lists their appointment.
    mine = client.get("/api/v1/appointments", headers=_auth(patient_token))
    assert mine.status_code == 200, mine.text
    assert [a["id"] for a in mine.json()] == [appt_id]

    # Doctor sees it on their calendar and confirms, then completes.
    doc_list = client.get("/api/v1/appointments", headers=_auth(doctor_token))
    assert [a["id"] for a in doc_list.json()] == [appt_id]
    confirm = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "CONFIRMED"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "CONFIRMED"
    complete = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "COMPLETED", "notes": "All good"},
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == "COMPLETED"
    assert complete.json()["notes"] == "All good"

    # Patient books a second slot then cancels it.
    book2 = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": _SECOND_SLOT_START.isoformat()},
    )
    assert book2.status_code == 201, book2.text
    appt2_id = book2.json()["id"]
    cancel = client.patch(
        f"/api/v1/appointments/{appt2_id}",
        headers=_auth(patient_token),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"


def test_non_doctor_cannot_add_availability(client: TestClient, db: sessionmaker[Session]) -> None:
    _, patient_token = _seed_patient(db, "book-patient2@sehaty.ma")
    resp = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(patient_token),
        json={"weekday": 0, "start_time": "09:00", "end_time": "12:00", "slot_minutes": 30},
    )
    assert resp.status_code == 403, resp.text
