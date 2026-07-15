"""Doctor dashboard API integration test over the in-memory SQLite fixture.

Non-geo (doctor-scoped stats), so it runs on the shared `client`/`db` fixtures.
A freshly-registered doctor with no appointments gets zeroed stats and a null
next appointment; a non-doctor is 403.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient) -> str:
    client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "dash-doc@clinic.ma",
            "password": "dash-pw-123",
            "full_name": "Dr Dashboard",
            "slug": "dr-dashboard",
            "license_no": "LIC-DASH-1",
            "phone": "+212613009999",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "dash-doc@clinic.ma", "password": "dash-pw-123"},
    )
    return login.json()["access"]


def test_doctor_dashboard_zeroed_for_new_doctor(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    token = _register_and_login_doctor(client)
    resp = client.get("/api/v1/doctor/dashboard", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["today_total"] == 0
    assert body["today_confirmed"] == 0
    assert body["to_confirm"] == 0
    assert body["upcoming_7d"] == 0
    assert body["patients_total"] == 0
    assert body["next_appointment"] is None


def test_doctor_dashboard_requires_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    with db() as session:
        patient = User(
            email="dash-patient@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    token = security.create_access_token(patient_id, UserRole.PATIENT)
    assert client.get("/api/v1/doctor/dashboard", headers=_auth(token)).status_code == 403
