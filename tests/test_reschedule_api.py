"""Appointment reschedule API tests over the in-memory SQLite fixture.

Covers both reschedule surfaces exposed by the API — the patient moving their own
appointment (``POST /appointments/{id}/reschedule``) and the doctor/assistant
moving one on the doctor's behalf (``POST /doctor/appointments/{id}/reschedule``,
resolved via ``get_acting_doctor_id``). The test doctor is pinned to the ``UTC``
timezone so the UTC wall-clock slots below are genuine free slots regardless of
the clinic-default ``Africa/Casablanca`` offset.

Flow: a patient books a slot; a patient move resets the status to REQUESTED and
lands on the new slot; moving onto a slot already taken by another appointment is
409; another patient is 403. A DOCTOR (and a linked ASSISTANT) move preserves the
status; an unlinked assistant and a patient on the doctor route are both 403.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.assistants import AssistantController
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

# A fixed future date well clear of "today" so the slot always lands in range.
_TARGET_DAY: date = date.today() + timedelta(days=7)
_SLOT_A = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)
_SLOT_B = _SLOT_A + timedelta(hours=1)  # 10:00Z, another free slot in the window


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"resc-doc-{suffix}@clinic.ma",
            "password": "resc-pw-123",
            "full_name": f"Dr Resc {suffix}",
            "slug": f"dr-resc-{suffix}",
            "license_no": f"LIC-RESC-{suffix}",
            "phone": f"+21261700{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"resc-doc-{suffix}@clinic.ma", "password": "resc-pw-123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access"]

    # Pin the clinic timezone to UTC so the UTC slots below are valid.
    put = client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(token),
        json={"full_name": f"Dr Resc {suffix}", "timezone": "UTC"},
    )
    assert put.status_code == 200, put.text
    return doctor_id, token


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


def _book(client: TestClient, patient_token: str, doctor_id: int, start: datetime) -> int:
    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": start.isoformat(), "reason": "Checkup"},
    )
    assert book.status_code == 201, book.text
    return int(book.json()["id"])


def test_patient_reschedule_moves_and_resets_status(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "1")
    _add_window(client, doctor_token)
    patient_id, patient_token = _seed_patient(db, "resc-patient1@sehaty.ma")

    appt_id = _book(client, patient_token, doctor_id, _SLOT_A)

    # Doctor confirms it, so the appointment is CONFIRMED before the move.
    confirm = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "CONFIRMED"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "CONFIRMED"

    # Patient reschedules to the free SLOT_B: it moves and resets to REQUESTED.
    resc = client.post(
        f"/api/v1/appointments/{appt_id}/reschedule",
        headers=_auth(patient_token),
        json={"new_start_at": _SLOT_B.isoformat(), "notes": "Please move me"},
    )
    assert resc.status_code == 200, resc.text
    body = resc.json()
    assert body["id"] == appt_id
    assert body["patient_id"] == patient_id
    assert body["status"] == "REQUESTED"
    assert datetime.fromisoformat(body["start_at"]) == _SLOT_B
    assert body["notes"] == "Please move me"

    # The move is durable on the patient's own listing (compare tz-agnostically:
    # the SQLite-backed listing serialises the instant without an offset).
    mine = client.get("/api/v1/appointments", headers=_auth(patient_token))
    listed = datetime.fromisoformat(mine.json()[0]["start_at"]).replace(tzinfo=None)
    assert listed == _SLOT_B.replace(tzinfo=None)


def test_patient_reschedule_to_taken_slot_is_409(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "2")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "resc-patient2@sehaty.ma")

    appt_a = _book(client, patient_token, doctor_id, _SLOT_A)
    _book(client, patient_token, doctor_id, _SLOT_B)  # SLOT_B is now taken.

    # Rescheduling appt_a onto the already-booked SLOT_B is a conflict.
    taken = client.post(
        f"/api/v1/appointments/{appt_a}/reschedule",
        headers=_auth(patient_token),
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert taken.status_code == 409, taken.text

    # A slot outside any availability window is likewise a conflict.
    invalid = client.post(
        f"/api/v1/appointments/{appt_a}/reschedule",
        headers=_auth(patient_token),
        json={"new_start_at": (_SLOT_A - timedelta(hours=4)).isoformat()},
    )
    assert invalid.status_code == 409, invalid.text


def test_other_patient_cannot_reschedule_is_403(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "3")
    _add_window(client, doctor_token)
    _owner_id, owner_token = _seed_patient(db, "resc-owner@sehaty.ma")
    _other_id, other_token = _seed_patient(db, "resc-other@sehaty.ma")

    appt_id = _book(client, owner_token, doctor_id, _SLOT_A)

    forbidden = client.post(
        f"/api/v1/appointments/{appt_id}/reschedule",
        headers=_auth(other_token),
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert forbidden.status_code == 403, forbidden.text


def test_doctor_reschedule_preserves_status(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "4")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "resc-patient4@sehaty.ma")

    appt_id = _book(client, patient_token, doctor_id, _SLOT_A)
    confirm = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers=_auth(doctor_token),
        json={"status": "CONFIRMED"},
    )
    assert confirm.status_code == 200, confirm.text

    # The doctor moves the appointment; a doctor move preserves the status.
    resc = client.post(
        f"/api/v1/doctor/appointments/{appt_id}/reschedule",
        headers=_auth(doctor_token),
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert resc.status_code == 200, resc.text
    assert resc.json()["status"] == "CONFIRMED"
    assert datetime.fromisoformat(resc.json()["start_at"]) == _SLOT_B


def test_assistant_reschedules_on_behalf(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "5")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "resc-patient5@sehaty.ma")
    appt_id = _book(client, patient_token, doctor_id, _SLOT_A)

    # Onboard a linked assistant, then log them in (role ASSISTANT).
    AssistantController.create_assistant_account(
        doctor_id=doctor_id,
        email="resc-secretary@clinic.ma",
        password="sec-pw-123",
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "resc-secretary@clinic.ma", "password": "sec-pw-123"},
    )
    assert login.status_code == 200, login.text
    assistant_token = login.json()["access"]

    # The assistant moves the appointment on the doctor's behalf (?doctor_id=).
    resc = client.post(
        f"/api/v1/doctor/appointments/{appt_id}/reschedule",
        headers=_auth(assistant_token),
        params={"doctor_id": doctor_id},
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert resc.status_code == 200, resc.text
    assert datetime.fromisoformat(resc.json()["start_at"]) == _SLOT_B


def test_unlinked_assistant_and_patient_on_doctor_route_are_403(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "6")
    _add_window(client, doctor_token)
    _patient_id, patient_token = _seed_patient(db, "resc-patient6@sehaty.ma")
    appt_id = _book(client, patient_token, doctor_id, _SLOT_A)

    unlinked_token = _seed_unlinked_assistant(db, "resc-unlinked@clinic.ma")

    # An assistant with no membership cannot act on the doctor's route.
    unlinked = client.post(
        f"/api/v1/doctor/appointments/{appt_id}/reschedule",
        headers=_auth(unlinked_token),
        params={"doctor_id": doctor_id},
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert unlinked.status_code == 403, unlinked.text

    # A patient is never allowed on the doctor route.
    patient = client.post(
        f"/api/v1/doctor/appointments/{appt_id}/reschedule",
        headers=_auth(patient_token),
        json={"new_start_at": _SLOT_B.isoformat()},
    )
    assert patient.status_code == 403, patient.text
