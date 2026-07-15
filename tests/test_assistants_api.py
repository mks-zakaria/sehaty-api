"""Assistant-management API integration tests over the in-memory SQLite fixture.

These routes are non-geo (doctor<->assistant membership + the assistant's doctor
list), so they run on the shared ``client``/``db`` fixtures without PostGIS — the
conftest builds the ``users`` + ``doctor_assistants`` tables. Flow under test: a
doctor onboards an assistant via ``POST`` and lists them; the assistant logs in
(email + password, role ASSISTANT) and sees the doctor via
``GET /assistant/doctors``; a non-doctor is 403 on the doctor surface and a
patient is 403 on the assistant surface; ``DELETE`` deactivates the membership
so the assistant is no longer listed.
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
            "email": f"asst-doc-{suffix}@clinic.ma",
            "password": "asst-pw-123",
            "full_name": f"Dr Assist {suffix}",
            "slug": f"dr-assist-{suffix}",
            "license_no": f"LIC-ASST-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"asst-doc-{suffix}@clinic.ma", "password": "asst-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_patient(db: sessionmaker[Session], email: str) -> str:
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
    return security.create_access_token(patient_id, UserRole.PATIENT)


def test_doctor_creates_and_lists_assistant(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "1")

    created = client.post(
        "/api/v1/doctor/assistants",
        headers=_auth(doctor_token),
        json={
            "email": "secretary1@clinic.ma",
            "phone": "+212611000001",
            "full_name": "Sara Secretary",
            "password": "sec-pw-123",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["email"] == "secretary1@clinic.ma"
    assert body["full_name"] == "Sara Secretary"
    assert body["is_active"] is True
    assistant_id = body["id"]

    listing = client.get("/api/v1/doctor/assistants", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert [r["id"] for r in rows] == [assistant_id]
    assert rows[0]["email"] == "secretary1@clinic.ma"


def test_assistant_sees_linked_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "2")

    created = client.post(
        "/api/v1/doctor/assistants",
        headers=_auth(doctor_token),
        json={"email": "secretary2@clinic.ma", "password": "sec-pw-123"},
    )
    assert created.status_code == 201, created.text

    # The assistant logs in with email + password and gets role ASSISTANT.
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "secretary2@clinic.ma", "password": "sec-pw-123"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["role"] == "ASSISTANT"
    assistant_token = login.json()["access"]

    doctors = client.get("/api/v1/assistant/doctors", headers=_auth(assistant_token))
    assert doctors.status_code == 200, doctors.text
    refs = doctors.json()
    assert [r["doctor_id"] for r in refs] == [doctor_id]
    assert refs[0]["full_name"] == "Dr Assist 2"


def test_role_gating(client: TestClient, db: sessionmaker[Session]) -> None:
    patient_token = _seed_patient(db, "asst-patient@sehaty.ma")

    # A non-doctor cannot onboard an assistant.
    denied = client.post(
        "/api/v1/doctor/assistants",
        headers=_auth(patient_token),
        json={"email": "nope@clinic.ma", "password": "pw"},
    )
    assert denied.status_code == 403, denied.text

    # A patient cannot hit the assistant surface.
    denied2 = client.get("/api/v1/assistant/doctors", headers=_auth(patient_token))
    assert denied2.status_code == 403, denied2.text


def test_delete_deactivates_membership(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "3")

    created = client.post(
        "/api/v1/doctor/assistants",
        headers=_auth(doctor_token),
        json={"email": "secretary3@clinic.ma", "password": "sec-pw-123"},
    )
    assert created.status_code == 201, created.text
    assistant_id = created.json()["id"]

    removed = client.delete(
        f"/api/v1/doctor/assistants/{assistant_id}", headers=_auth(doctor_token)
    )
    assert removed.status_code == 204, removed.text

    listing = client.get("/api/v1/doctor/assistants", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    assert listing.json() == []

    # Removing an already-inactive membership is a 404.
    again = client.delete(f"/api/v1/doctor/assistants/{assistant_id}", headers=_auth(doctor_token))
    assert again.status_code == 404, again.text
