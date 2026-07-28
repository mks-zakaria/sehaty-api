"""Waitlist API: the loop from a freed slot to the patient who takes it.

The doctor's day view can free a slot and offer it in one call, but until the
patient it was offered to can *see* the offer, the loop does not close: the
queue moves on, the offer expires, and the slot stays empty. That round trip —
join, release, see, accept — is what these tests hold in place, along with the
rule that ``/waitlist/me`` never shows one patient another's entries.
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_TARGET_DAY: date = date.today() + timedelta(days=7)
_SLOT = datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"wl-doc-{suffix}@clinic.ma",
            "password": "wl-pw-12345",
            "full_name": f"Dr Waitlist {suffix}",
            "slug": f"dr-waitlist-{suffix}",
            "license_no": f"LIC-WL-{suffix}",
            "phone": f"+21261800{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"wl-doc-{suffix}@clinic.ma", "password": "wl-pw-12345"},
    )
    token = login.json()["access"]
    # UTC so the slot below is genuinely bookable.
    client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(token),
        json={"full_name": f"Dr Waitlist {suffix}", "timezone": "UTC"},
    )
    client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "12:00",
            "slot_minutes": 30,
        },
    )
    return int(reg.json()["id"]), token


def _patient(db: sessionmaker[Session], email: str) -> tuple[int, str]:
    with db() as session:
        user = User(email=email, role=UserRole.PATIENT, is_active=True, password_hash="x")
        session.add(user)
        session.commit()
        uid = int(user.id)
    return uid, security.create_access_token(uid, UserRole.PATIENT)


def test_a_released_slot_reaches_the_patient_who_can_then_take_it(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _doctor(client, "1")
    _, booked_token = _patient(db, "wl-booked1@sehaty.ma")
    _, waiting_token = _patient(db, "wl-waiting1@sehaty.ma")

    book = client.post(
        "/api/v1/appointments",
        headers=_auth(booked_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT.isoformat(), "reason": "Checkup"},
    )
    assert book.status_code == 201, book.text
    appointment_id = int(book.json()["id"])

    join = client.post(
        "/api/v1/waitlist", headers=_auth(waiting_token), json={"doctor_id": doctor_id}
    )
    assert join.status_code == 201, join.text
    entry_id = join.json()["entry_id"]

    # Waiting, with nothing on the table yet.
    mine = client.get("/api/v1/waitlist/me", headers=_auth(waiting_token))
    assert mine.status_code == 200, mine.text
    assert [r["status"] for r in mine.json()] == ["WAITING"]
    assert mine.json()[0]["offered_start_at"] is None

    release = client.post(
        f"/api/v1/appointments/{appointment_id}/release", headers=_auth(doctor_token)
    )
    assert release.status_code == 200, release.text
    assert release.json()["offered"] is True

    # The offer is now visible to the patient, with the slot and the deadline.
    offered = client.get("/api/v1/waitlist/me", headers=_auth(waiting_token)).json()
    assert offered[0]["status"] == "OFFERED"
    assert offered[0]["offered_start_at"] is not None
    assert offered[0]["offer_expires_at"] is not None
    assert offered[0]["doctor_slug"] == "dr-waitlist-1"

    accept = client.post(f"/api/v1/waitlist/{entry_id}/accept", headers=_auth(waiting_token))
    assert accept.status_code == 200, accept.text
    assert accept.json()["appointment_id"]

    # Taken: the entry leaves the list rather than lingering as a live offer.
    assert client.get("/api/v1/waitlist/me", headers=_auth(waiting_token)).json() == []


def test_me_never_shows_another_patients_entries(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, _ = _doctor(client, "2")
    _, mine_token = _patient(db, "wl-mine@sehaty.ma")
    _, theirs_token = _patient(db, "wl-theirs@sehaty.ma")

    for token in (mine_token, theirs_token):
        assert (
            client.post(
                "/api/v1/waitlist", headers=_auth(token), json={"doctor_id": doctor_id}
            ).status_code
            == 201
        )

    assert len(client.get("/api/v1/waitlist/me", headers=_auth(mine_token)).json()) == 1


def test_me_requires_a_patient(client: TestClient) -> None:
    _, doctor_token = _doctor(client, "3")

    assert client.get("/api/v1/waitlist/me").status_code == 401
    assert client.get("/api/v1/waitlist/me", headers=_auth(doctor_token)).status_code == 403


def test_declining_keeps_the_place_in_the_queue(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _doctor(client, "4")
    _, booked_token = _patient(db, "wl-booked4@sehaty.ma")
    _, waiting_token = _patient(db, "wl-waiting4@sehaty.ma")

    book = client.post(
        "/api/v1/appointments",
        headers=_auth(booked_token),
        json={"doctor_id": doctor_id, "start_at": _SLOT.isoformat(), "reason": "Checkup"},
    )
    entry_id = client.post(
        "/api/v1/waitlist", headers=_auth(waiting_token), json={"doctor_id": doctor_id}
    ).json()["entry_id"]
    client.post(
        f"/api/v1/appointments/{int(book.json()['id'])}/release", headers=_auth(doctor_token)
    )

    decline = client.post(f"/api/v1/waitlist/{entry_id}/decline", headers=_auth(waiting_token))
    assert decline.status_code == 204, decline.text

    # Turning one slot down is not leaving the list — a patient who declines a
    # Tuesday 9am still wants a Thursday one.
    still = client.get("/api/v1/waitlist/me", headers=_auth(waiting_token)).json()
    assert [r["status"] for r in still] == ["WAITING"]
    assert still[0]["offered_start_at"] is None
