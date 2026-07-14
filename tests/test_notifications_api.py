"""In-app notification API integration tests over a TestClient with in-memory
SQLite.

The notification surface is non-geo — the bell feed, unread badge and mark-read
are keyed by numeric user/notification ids — so it runs on the in-memory SQLite
``client``/``db`` fixtures. Every route is scoped to the calling authenticated
user. Covers: the feed returned newest-first with ``unread_only`` filtering and
the unread badge; ``POST /{id}/read`` flipping a single row and decrementing the
badge; ``POST /read-all`` clearing the badge; and the ownership rule (a user
cannot mark another user's notification read -> 403).
"""

from fastapi.testclient import TestClient
from sehaty.core.controllers.notifications import NotificationController
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_DOCTOR = {
    "email": "notif-doc@clinic.ma",
    "password": "notif-pw-123",
    "full_name": "Dr Notify",
    "slug": "dr-notify",
    "license_no": "LIC-NOTIF-1",
    "phone": "+212600004321",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient) -> tuple[int, str]:
    reg = client.post("/api/v1/auth/doctor/register", json=_DOCTOR)
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": _DOCTOR["email"], "password": _DOCTOR["password"]},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_patient(db: sessionmaker[Session], email: str = "notif-patient@sehaty.ma") -> int:
    with db() as session:
        patient = User(email=email, role=UserRole.PATIENT, is_active=True, password_hash="unused")
        session.add(patient)
        session.commit()
        return int(patient.id)


def test_feed_newest_first_and_unread_filter(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client)

    first = NotificationController.notify(doctor_id, "booking", "Appointment confirmed")
    second = NotificationController.notify(doctor_id, "review", "New review received")
    first_id, second_id = int(first.id), int(second.id)

    feed = client.get("/api/v1/notifications", headers=_auth(doctor_token))
    assert feed.status_code == 200, feed.text
    body = feed.json()
    assert [n["id"] for n in body] == [second_id, first_id]
    assert body[0]["kind"] == "review"
    assert all(n["is_read"] is False for n in body)

    # Unread badge reflects both unread rows.
    count = client.get("/api/v1/notifications/unread-count", headers=_auth(doctor_token))
    assert count.status_code == 200, count.text
    assert count.json() == {"unread": 2}

    # Mark one read, then unread_only should hide it.
    NotificationController.mark_read(doctor_id, first_id)
    unread = client.get(
        "/api/v1/notifications",
        headers=_auth(doctor_token),
        params={"unread_only": True},
    )
    assert unread.status_code == 200, unread.text
    assert [n["id"] for n in unread.json()] == [second_id]


def test_mark_read_flips_and_decrements_badge(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client)
    NotificationController.notify(doctor_id, "booking", "Appointment confirmed")
    target = NotificationController.notify(doctor_id, "payment", "Payment recorded")
    target_id = int(target.id)

    before = client.get("/api/v1/notifications/unread-count", headers=_auth(doctor_token))
    assert before.json() == {"unread": 2}

    read = client.post(f"/api/v1/notifications/{target_id}/read", headers=_auth(doctor_token))
    assert read.status_code == 200, read.text
    row = read.json()
    assert row["id"] == target_id
    assert row["is_read"] is True

    after = client.get("/api/v1/notifications/unread-count", headers=_auth(doctor_token))
    assert after.json() == {"unread": 1}


def test_read_all_clears_badge(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client)
    NotificationController.notify(doctor_id, "booking", "Appointment confirmed")
    NotificationController.notify(doctor_id, "review", "New review received")

    marked = client.post("/api/v1/notifications/read-all", headers=_auth(doctor_token))
    assert marked.status_code == 200, marked.text
    assert marked.json() == {"marked": 2}

    count = client.get("/api/v1/notifications/unread-count", headers=_auth(doctor_token))
    assert count.json() == {"unread": 0}


def test_cannot_read_another_users_notification(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client)
    patient_id = _seed_patient(db)

    # A notification that belongs to the patient, not the calling doctor.
    foreign = NotificationController.notify(patient_id, "system", "Welcome to Sehaty")
    foreign_id = int(foreign.id)

    resp = client.post(f"/api/v1/notifications/{foreign_id}/read", headers=_auth(doctor_token))
    assert resp.status_code == 403, resp.text
