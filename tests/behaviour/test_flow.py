"""End-to-end behaviour suite — grows one slice per feature.

Step 1: a doctor registers, logs in, and reads their own identity via /me.
Later slices append steps (appointments, prescriptions, ...).
"""

from fastapi.testclient import TestClient


def test_flow_register_login_me(client: TestClient) -> None:
    # Step 1 — register a doctor -> login -> call /me.
    register = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "flow-doc@clinic.ma",
            "password": "flow-pw-123",
            "full_name": "Dr Flow",
            "slug": "dr-flow",
            "license_no": "LIC-FLOW-1",
            "phone": "+212612345678",
        },
    )
    assert register.status_code == 201, register.text

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "flow-doc@clinic.ma", "password": "flow-pw-123"},
    )
    assert login.status_code == 200, login.text
    access = login.json()["access"]

    me = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "DOCTOR"
    assert me.json()["email"] == "flow-doc@clinic.ma"
