"""Doctor analytics API integration test over the in-memory SQLite fixture.

Non-geo (doctor-scoped stats), so it runs on the shared `client`/`db` fixtures.
A freshly-registered doctor with no data gets zero-filled monthly buckets and a
zero no-show rate; a non-doctor is 403.
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
            "email": "analytics-doc@clinic.ma",
            "password": "analytics-pw-123",
            "full_name": "Dr Analytics",
            "slug": "dr-analytics",
            "license_no": "LIC-ANALYTICS-1",
            "phone": "+212613008888",
        },
    )
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "analytics-doc@clinic.ma", "password": "analytics-pw-123"},
    )
    return login.json()["access"]


def test_doctor_analytics_zeroed_for_new_doctor(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    token = _register_and_login_doctor(client)
    resp = client.get("/api/v1/doctor/analytics", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["by_month"]) == 6
    assert len(body["reviews_by_month"]) == 6
    assert body["no_show_rate"] == 0
    assert body["total_appointments"] == 0
    assert body["total_completed"] == 0
    assert body["total_no_show"] == 0
    assert body["avg_rating"] == 0
    assert body["review_count"] == 0
    for month in body["by_month"]:
        assert month["total"] == 0
        assert month["completed"] == 0
        assert month["no_show"] == 0
        assert month["cancelled"] == 0
        assert month["estimated_revenue"] == 0
    for month in body["reviews_by_month"]:
        assert month["count"] == 0


def test_doctor_analytics_respects_months_query(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    token = _register_and_login_doctor(client)
    resp = client.get("/api/v1/doctor/analytics?months=3", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["by_month"]) == 3
    assert len(body["reviews_by_month"]) == 3


def test_doctor_analytics_requires_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    with db() as session:
        patient = User(
            email="analytics-patient@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    token = security.create_access_token(patient_id, UserRole.PATIENT)
    assert client.get("/api/v1/doctor/analytics", headers=_auth(token)).status_code == 403
