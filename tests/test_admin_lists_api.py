"""Admin Users/Subscriptions listing API tests over a TestClient with SQLite.

Seeds an admin, a doctor (with a ``DoctorProfile`` so the row carries a
``full_name``), a patient, a plan and a subscription directly via the session
factory (the shared fixtures build users, doctor_profiles, plans and
subscriptions). Covers: the admin Users listing (and the ``?role=DOCTOR``
filter), the admin Subscriptions listing (doctor_name + plan_name resolved via
the joins), and role gating (a non-admin on either route -> 403).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import (
    DoctorProfile,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy.orm import Session, sessionmaker


def _dt(month: int, day: int = 15) -> datetime:
    return datetime(2026, month, day, 10, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        admin = User(
            email="lists-admin@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _seed_patient_token(db: sessionmaker[Session]) -> str:
    with db() as session:
        patient = User(
            email="lists-patient2@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return security.create_access_token(patient_id, UserRole.PATIENT)


def _seed_fixture(db: sessionmaker[Session]) -> dict[str, int]:
    """A verified doctor (with profile), a patient, a plan and a subscription."""
    ids: dict[str, int] = {}
    with db() as s:
        doctor = User(email="lists-doc@clinic.ma", role=UserRole.DOCTOR, is_active=True)
        patient = User(email="lists-pat@sehaty.ma", role=UserRole.PATIENT, is_active=True)
        s.add_all([doctor, patient])
        s.flush()
        ids.update(doctor=int(doctor.id), patient=int(patient.id))

        s.add(
            DoctorProfile(
                user_id=doctor.id,
                full_name="Dr Lister",
                slug="dr-lister",
                license_no="LIC-LIST-1",
                verification_status=VerificationStatus.VERIFIED,
            )
        )

        plan = Plan(code="essentiel", name="Essentiel", price_month=199.0, currency="MAD")
        s.add(plan)
        s.flush()
        subscription = Subscription(
            doctor_id=doctor.id,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=_dt(1),
            current_period_end=_dt(2),
        )
        s.add(subscription)
        s.commit()
        ids["subscription"] = int(subscription.id)
    return ids


def test_admin_lists_users(client: TestClient, db: sessionmaker[Session]) -> None:
    ids = _seed_fixture(db)
    token = _seed_admin(db)

    resp = client.get("/api/v1/admin/users", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    listed = {row["id"] for row in rows}
    assert ids["doctor"] in listed
    assert ids["patient"] in listed

    doctor_row = next(r for r in rows if r["id"] == ids["doctor"])
    assert doctor_row["role"] == "DOCTOR"
    assert doctor_row["full_name"] == "Dr Lister"
    assert doctor_row["email"] == "lists-doc@clinic.ma"


def test_admin_users_role_filter(client: TestClient, db: sessionmaker[Session]) -> None:
    ids = _seed_fixture(db)
    token = _seed_admin(db)

    resp = client.get("/api/v1/admin/users", params={"role": "DOCTOR"}, headers=_auth(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert {r["id"] for r in rows} == {ids["doctor"]}
    assert all(r["role"] == "DOCTOR" for r in rows)


def test_admin_lists_subscriptions(client: TestClient, db: sessionmaker[Session]) -> None:
    ids = _seed_fixture(db)
    token = _seed_admin(db)

    resp = client.get("/api/v1/admin/subscriptions", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    row = next(r for r in rows if r["id"] == ids["subscription"])
    assert row["doctor_id"] == ids["doctor"]
    assert row["doctor_name"] == "Dr Lister"
    assert row["plan_code"] == "essentiel"
    assert row["plan_name"] == "Essentiel"
    assert row["price_month"] == 199.0
    assert row["currency"] == "MAD"
    assert row["status"] == "ACTIVE"


def test_non_admin_hitting_lists_is_403(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed_fixture(db)
    patient_token = _seed_patient_token(db)

    for path in ("/users", "/subscriptions"):
        resp = client.get(f"/api/v1/admin{path}", headers=_auth(patient_token))
        assert resp.status_code == 403, resp.text
