"""End-to-end behaviour suite — grows one slice per feature.

Step 1: a doctor registers, logs in, and reads their own identity via /me.
Step 2: an admin accredits that doctor -> the doctor is now verified.
Step 3: the (verified) doctor sets their profile + location -> the public page
        resolves by slug with the round-tripped coordinates. This slice needs
        the real PostGIS ``geopoint`` column, so it takes the ``pg_*`` fixtures
        and SKIPs when no database is reachable.
Later slices append steps (appointments, prescriptions, ...).
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.admin import AdminController
from sehaty.core.controllers.specialties import SpecialtyController
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker


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


def test_flow_admin_accredits_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    # Step 2 — register a doctor, then an admin accredits them -> verified.
    register = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "flow-doc2@clinic.ma",
            "password": "flow-pw-123",
            "full_name": "Dr Flow Two",
            "slug": "dr-flow-two",
            "license_no": "LIC-FLOW-2",
            "phone": "+212612345679",
        },
    )
    assert register.status_code == 201, register.text
    doctor_id = int(register.json()["id"])
    assert AdminController.is_doctor_verified(doctor_id) is False

    # Seed an admin and mint an access token for them.
    with db() as session:
        admin = User(
            email="flow-admin@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_token = security.create_access_token(int(admin.id), UserRole.ADMIN)

    accredit = client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert accredit.status_code == 200, accredit.text
    assert AdminController.is_doctor_verified(doctor_id) is True


def test_flow_doctor_profile_public_page(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    # Step 3 — register -> login -> accredit, then the doctor sets their
    # profile + location and the public page resolves by slug (PostGIS).
    SpecialtyController.seed_defaults()

    register = pg_client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "flow-doc3@clinic.ma",
            "password": "flow-pw-123",
            "full_name": "Dr Flow Three",
            "slug": "dr-flow-three",
            "license_no": "LIC-FLOW-3",
            "phone": "+212612345680",
        },
    )
    assert register.status_code == 201, register.text
    doctor_id = int(register.json()["id"])

    login = pg_client.post(
        "/api/v1/auth/login",
        json={"email": "flow-doc3@clinic.ma", "password": "flow-pw-123"},
    )
    assert login.status_code == 200, login.text
    access = login.json()["access"]

    with pg_db() as session:
        admin = User(
            email="flow-admin3@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_token = security.create_access_token(int(admin.id), UserRole.ADMIN)

    lat, lng = 34.020882, -6.841650  # Rabat
    put = pg_client.put(
        "/api/v1/doctors/me/profile",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "full_name": "Dr Flow Three",
            "city": "Rabat",
            "lat": lat,
            "lng": lng,
            "specialty_slugs": ["generalist"],
        },
    )
    assert put.status_code == 200, put.text
    slug = put.json()["slug"]

    accredit = pg_client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert accredit.status_code == 200, accredit.text

    page = pg_client.get(f"/api/v1/doctors/{slug}")
    assert page.status_code == 200, page.text
    body = page.json()
    assert body["slug"] == slug
    assert body["city"] == "Rabat"
    assert abs(body["lat"] - lat) < 1e-6
    assert abs(body["lng"] - lng) < 1e-6
    assert {s["slug"] for s in body["specialties"]} == {"generalist"}
