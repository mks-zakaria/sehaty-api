"""End-to-end behaviour suite — grows one slice per feature.

Step 1: a doctor registers, logs in, and reads their own identity via /me.
Step 2: an admin accredits that doctor -> the doctor is now verified.
Step 3: the (verified) doctor sets their profile + location -> the public page
        resolves by slug with the round-tripped coordinates, and a patient
        searching that specialty near the doctor finds them in the ranked
        results. This slice needs the real PostGIS ``geopoint`` column, so it
        takes the ``pg_*`` fixtures and SKIPs when no database is reachable.
Step 4: after registering + accrediting a doctor, the doctor sets a weekly
        availability window, a patient books one of the derived slots, and the
        doctor confirms it. Booking is non-geo, so this slice runs on the SQLite
        ``client``/``db`` fixtures (no PostGIS, no profile/geo needed).
Later slices append steps (prescriptions, ...).
"""

from datetime import UTC, date, datetime, timedelta

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

    # A patient searches that specialty near the doctor -> finds them ranked.
    search = pg_client.get(
        "/api/v1/doctors",
        params={"specialty": "generalist", "lat": lat, "lng": lng},
    )
    assert search.status_code == 200, search.text
    hits = search.json()
    assert slug in {h["slug"] for h in hits}
    found = next(h for h in hits if h["slug"] == slug)
    assert found["distance_m"] < 100  # the search origin is the doctor's point
    assert "rank" in found


def test_flow_booking(client: TestClient, db: sessionmaker[Session]) -> None:
    # Step 4 — register + accredit a doctor, who then opens a weekly
    # availability window; a patient books a derived slot and the doctor
    # confirms it. Non-geo, so this runs on the SQLite fixtures.
    register = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": "flow-doc4@clinic.ma",
            "password": "flow-pw-123",
            "full_name": "Dr Flow Four",
            "slug": "dr-flow-four",
            "license_no": "LIC-FLOW-4",
            "phone": "+212612345681",
        },
    )
    assert register.status_code == 201, register.text
    doctor_id = int(register.json()["id"])

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "flow-doc4@clinic.ma", "password": "flow-pw-123"},
    )
    assert login.status_code == 200, login.text
    doctor_token = login.json()["access"]

    # An admin accredits the doctor.
    with db() as session:
        admin = User(
            email="flow-admin4@sehaty.ma",
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

    # The doctor opens a weekly availability window.
    target_day = date.today() + timedelta(days=5)
    add = client.post(
        "/api/v1/doctors/me/availability",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={
            "weekday": target_day.weekday(),
            "start_time": "10:00",
            "end_time": "11:00",
            "slot_minutes": 30,
        },
    )
    assert add.status_code == 201, add.text

    # The public slots endpoint expands the window.
    slots = client.get(
        f"/api/v1/doctors/{doctor_id}/slots",
        params={"from": target_day.isoformat(), "to": target_day.isoformat()},
    )
    assert slots.status_code == 200, slots.text
    slot_start_dt = datetime(target_day.year, target_day.month, target_day.day, 10, 0, tzinfo=UTC)
    slot_start = slot_start_dt.isoformat()
    assert slot_start_dt in {datetime.fromisoformat(s["start_at"]) for s in slots.json()}

    # A patient books that slot.
    with db() as session:
        patient = User(
            email="flow-patient4@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_token = security.create_access_token(int(patient.id), UserRole.PATIENT)
    book = client.post(
        "/api/v1/appointments",
        headers={"Authorization": f"Bearer {patient_token}"},
        json={"doctor_id": doctor_id, "start_at": slot_start, "reason": "First visit"},
    )
    assert book.status_code == 201, book.text
    appt_id = book.json()["id"]
    assert book.json()["status"] == "REQUESTED"

    # The doctor confirms the appointment.
    confirm = client.patch(
        f"/api/v1/appointments/{appt_id}",
        headers={"Authorization": f"Bearer {doctor_token}"},
        json={"status": "CONFIRMED"},
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["status"] == "CONFIRMED"
