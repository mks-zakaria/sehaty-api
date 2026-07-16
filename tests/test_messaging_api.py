"""Messaging API integration tests over the in-memory SQLite fixture.

Non-geo (threads + messages + read watermarks), so these run on the shared
``client``/``db`` fixtures without PostGIS — the conftest builds the
``message_threads`` + ``messages`` tables. Flow under test: a patient opens a
thread (idempotently) and posts; the clinic side sees unread, reads it (mine is
false, unread zeroes) and replies; the patient's unread then lifts until they
read; empty bodies 422; a stranger is 403 on someone else's thread; and role
gating rejects a non-patient on the patient surface and a non-clinic caller on
the clinic surface. An assistant linked to the doctor drives the clinic surface
with their own sender id.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"msg-doc-{suffix}@clinic.ma",
            "password": "msg-pw-123",
            "full_name": f"Dr Message {suffix}",
            "slug": f"dr-message-{suffix}",
            "license_no": f"LIC-MSG-{suffix}",
            "phone": f"+21261500{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"msg-doc-{suffix}@clinic.ma", "password": "msg-pw-123"},
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


def test_patient_starts_thread_is_idempotent(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, _doctor_token = _register_and_login_doctor(client, "1")
    _patient_id, patient_token = _seed_patient(db, "msg-p1@sehaty.ma")

    first = client.post(
        "/api/v1/patient/messages",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id},
    )
    assert first.status_code == 200, first.text
    thread_id = first.json()["id"]
    assert first.json()["doctor_id"] == doctor_id

    again = client.post(
        "/api/v1/patient/messages",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id},
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == thread_id


def test_full_conversation_unread_and_read_watermarks(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "2")
    _patient_id, patient_token = _seed_patient(db, "msg-p2@sehaty.ma")

    thread_id = client.post(
        "/api/v1/patient/messages",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id},
    ).json()["id"]

    # Patient posts a message.
    posted = client.post(
        f"/api/v1/patient/messages/{thread_id}",
        headers=_auth(patient_token),
        json={"body": "Hello doctor, I have a question."},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["mine"] is True

    # Doctor lists threads and sees unread >= 1.
    threads = client.get("/api/v1/doctor/messages", headers=_auth(doctor_token))
    assert threads.status_code == 200, threads.text
    assert threads.json()[0]["unread"] >= 1

    # Doctor opens the thread: the patient's message reads with mine=false.
    detail = client.get(f"/api/v1/doctor/messages/{thread_id}", headers=_auth(doctor_token))
    assert detail.status_code == 200, detail.text
    assert any(m["mine"] is False for m in detail.json()["messages"])

    # Doctor unread total is now 0.
    doc_unread = client.get("/api/v1/doctor/messages/unread", headers=_auth(doctor_token))
    assert doc_unread.status_code == 200, doc_unread.text
    assert doc_unread.json()["unread"] == 0

    # Doctor replies -> patient unread lifts.
    reply = client.post(
        f"/api/v1/doctor/messages/{thread_id}",
        headers=_auth(doctor_token),
        json={"body": "Sure, tell me more."},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["mine"] is True

    pat_unread = client.get("/api/v1/patient/messages/unread", headers=_auth(patient_token))
    assert pat_unread.json()["unread"] >= 1

    # Patient reads the thread -> unread zeroes; the reply shows mine=false.
    pat_detail = client.get(f"/api/v1/patient/messages/{thread_id}", headers=_auth(patient_token))
    assert pat_detail.status_code == 200, pat_detail.text
    assert any(
        m["body"] == "Sure, tell me more." and m["mine"] is False
        for m in pat_detail.json()["messages"]
    )
    assert (
        client.get("/api/v1/patient/messages/unread", headers=_auth(patient_token)).json()["unread"]
        == 0
    )


def test_empty_body_is_rejected(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, _doctor_token = _register_and_login_doctor(client, "3")
    _patient_id, patient_token = _seed_patient(db, "msg-p3@sehaty.ma")
    thread_id = client.post(
        "/api/v1/patient/messages",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id},
    ).json()["id"]

    resp = client.post(
        f"/api/v1/patient/messages/{thread_id}",
        headers=_auth(patient_token),
        json={"body": "   "},
    )
    assert resp.status_code in (400, 422), resp.text


def test_stranger_cannot_read_others_thread(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, _doctor_token = _register_and_login_doctor(client, "4")
    _p1_id, p1_token = _seed_patient(db, "msg-owner@sehaty.ma")
    _p2_id, p2_token = _seed_patient(db, "msg-stranger@sehaty.ma")

    thread_id = client.post(
        "/api/v1/patient/messages",
        headers=_auth(p1_token),
        json={"doctor_id": doctor_id},
    ).json()["id"]

    # A third, unrelated patient hitting the owner's thread is forbidden/not-found.
    got = client.get(f"/api/v1/patient/messages/{thread_id}", headers=_auth(p2_token))
    assert got.status_code in (403, 404), got.text
    posted = client.post(
        f"/api/v1/patient/messages/{thread_id}",
        headers=_auth(p2_token),
        json={"body": "peeking"},
    )
    assert posted.status_code in (403, 404), posted.text


def test_role_gating(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "5")
    _patient_id, patient_token = _seed_patient(db, "msg-p5@sehaty.ma")

    # A non-patient (doctor) on the patient surface -> 403.
    assert client.get("/api/v1/patient/messages", headers=_auth(doctor_token)).status_code == 403

    # A non-clinic caller (patient) on the clinic surface -> 403.
    assert client.get("/api/v1/doctor/messages", headers=_auth(patient_token)).status_code == 403


def test_assistant_drives_clinic_surface(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "6")
    _patient_id, patient_token = _seed_patient(db, "msg-p6@sehaty.ma")

    # Doctor onboards an assistant (created + linked).
    created = client.post(
        "/api/v1/doctor/assistants",
        headers=_auth(doctor_token),
        json={
            "email": "msg-secretary@clinic.ma",
            "phone": "+212611600006",
            "full_name": "Salma Secretary",
            "password": "sec-pw-123",
        },
    )
    assert created.status_code == 201, created.text
    assistant_id = created.json()["id"]
    asst_login = client.post(
        "/api/v1/auth/login",
        json={"email": "msg-secretary@clinic.ma", "password": "sec-pw-123"},
    )
    assert asst_login.status_code == 200, asst_login.text
    asst_token = asst_login.json()["access"]

    # Patient opens a thread and posts.
    thread_id = client.post(
        "/api/v1/patient/messages",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id},
    ).json()["id"]
    client.post(
        f"/api/v1/patient/messages/{thread_id}",
        headers=_auth(patient_token),
        json={"body": "Question for the clinic."},
    )

    # The assistant sees the thread on the resolved doctor's inbox with unread.
    listing = client.get("/api/v1/doctor/messages", headers=_auth(asst_token))
    assert listing.status_code == 200, listing.text
    assert listing.json()[0]["unread"] >= 1

    # The assistant replies; the message carries the assistant's own sender id.
    reply = client.post(
        f"/api/v1/doctor/messages/{thread_id}",
        headers=_auth(asst_token),
        json={"body": "The doctor will call you back."},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["sender_id"] == assistant_id
    assert reply.json()["mine"] is True
