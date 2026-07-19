"""Cabinet + consultation flow API integration test (in-memory SQLite fixture).

Drives the whole desk flow over HTTP: a doctor creates a cabinet and opens a
session (goes online), a checked-in patient appears in the doctor's queue, and
the doctor starts and completes the consultation, recording the encounter.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.db import Appointment, AppointmentStatus, ClinicPatient
from sqlalchemy.orm import Session, sessionmaker

_SLOT = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_doctor(client: TestClient) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "cabinet-doc@clinic.ma",
            "password": "cabinet-pw-123",
            "full_name": "Dr Cabinet",
            "slug": "dr-cabinet",
            "license_no": "LIC-CABINET-1",
            "phone": "+212613009999",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = reg.json()["id"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "cabinet-doc@clinic.ma", "password": "cabinet-pw-123"},
    )
    return doctor_id, login.json()["access"]


def test_cabinet_consultation_flow(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, token = _register_doctor(client)
    h = _auth(token)

    cab = client.post("/api/v1/cabinets", json={"name": "Cabinet A"}, headers=h)
    assert cab.status_code == 201, cab.text
    cabinet_id = cab.json()["id"]

    sess = client.post(f"/api/v1/cabinets/{cabinet_id}/sessions", json={}, headers=h)
    assert sess.status_code == 201, sess.text
    assert sess.json()["is_open"] is True
    session_id = sess.json()["id"]

    # Seed a register patient + a CONFIRMED appointment for this doctor.
    with db() as s:
        cp = ClinicPatient(
            doctor_id=doctor_id,
            full_name="Nadia K.",
            phone="+212600111222",
            sex="F",
            birth_year=1988,
        )
        s.add(cp)
        s.flush()
        appt = Appointment(
            patient_id=doctor_id,
            doctor_id=doctor_id,
            clinic_patient_id=cp.id,
            start_at=_SLOT,
            end_at=_SLOT + timedelta(minutes=30),
            status=AppointmentStatus.CONFIRMED,
        )
        s.add(appt)
        s.commit()
        appointment_id = appt.id

    # Secretary/doctor checks the patient in.
    ci = client.post(
        f"/api/v1/consultations/{appointment_id}/check-in",
        json={"cabinet_session_id": session_id},
        headers=h,
    )
    assert ci.status_code == 200, ci.text
    assert ci.json()["status"] == "CHECKED_IN"

    # Patient appears in the doctor's queue with their profile.
    q = client.get("/api/v1/consultations/queue", headers=h)
    assert q.status_code == 200, q.text
    queue = q.json()
    assert any(
        r["appointment_id"] == appointment_id and r["patient_name"] == "Nadia K." for r in queue
    )

    # Start the consultation.
    st = client.post(f"/api/v1/consultations/{appointment_id}/start", headers=h)
    assert st.status_code == 200, st.text
    assert st.json()["status"] == "IN_PROGRESS"
    assert st.json()["consultation_started_at"] is not None

    # Complete + record the encounter.
    comp = client.post(
        f"/api/v1/consultations/{appointment_id}/complete",
        json={"chief_complaint": "cough", "vitals": {"temp_c": 38.1}},
        headers=h,
    )
    assert comp.status_code == 200, comp.text
    body = comp.json()
    assert body["status"] == "COMPLETED"
    assert body["chief_complaint"] == "cough"
    assert body["vitals"]["temp_c"] == 38.1
    assert body["consultation_ended_at"] is not None

    # Queue is empty once the patient has been seen.
    assert client.get("/api/v1/consultations/queue", headers=h).json() == []


def test_waiting_count_threshold_and_alert(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, token = _register_doctor(client)
    h = _auth(token)
    cab = client.post("/api/v1/cabinets", json={"name": "WR"}, headers=h).json()
    cid = cab["id"]

    # Doctor sets an alert threshold.
    thr = client.put(f"/api/v1/cabinets/{cid}/alert-threshold", json={"threshold": 3}, headers=h)
    assert thr.status_code == 200, thr.text
    assert thr.json()["waiting_alert_threshold"] == 3

    # Below the threshold: count updates, no alert.
    r = client.post(f"/api/v1/cabinets/{cid}/waiting-count", json={"count": 2}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["waiting_room_count"] == 2
    assert client.get("/api/v1/notifications?unread_only=true", headers=h).json() == []

    # Crossing the threshold while offline: the owner is alerted.
    r = client.post(f"/api/v1/cabinets/{cid}/waiting-count", json={"count": 4}, headers=h)
    assert r.json()["waiting_room_count"] == 4
    notifs = client.get("/api/v1/notifications", headers=h).json()
    assert any(n["kind"] == "waiting_room_alert" for n in notifs)


def test_active_session_endpoint(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, token = _register_doctor(client)
    h = _auth(token)
    cab = client.post("/api/v1/cabinets", json={"name": "C"}, headers=h).json()

    # Nobody online yet -> null.
    assert client.get("/api/v1/consultations/active-session", headers=h).json() is None

    sess = client.post(f"/api/v1/cabinets/{cab['id']}/sessions", json={}, headers=h).json()
    got = client.get("/api/v1/consultations/active-session", headers=h).json()
    assert got is not None
    assert got["id"] == sess["id"]
    assert got["is_open"] is True
