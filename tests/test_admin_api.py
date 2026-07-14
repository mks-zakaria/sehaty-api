"""Admin/accreditation API tests over a TestClient with in-memory SQLite.

Covers role gating (only ADMIN may reach ``/api/v1/admin`` routes), the pending
queue listing, the accredit happy path (afterwards the doctor is VERIFIED), and
a 404 when accrediting a user with no doctor profile.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.admin import AdminController
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_DOCTOR = {
    "email": "pending-doc@clinic.ma",
    "password": "pw-doctor-123",
    "full_name": "Dr Pending",
    "slug": "dr-pending",
    "license_no": "LIC-PENDING-1",
    "phone": "+212600000009",
}


def _register_pending_doctor(client: TestClient) -> int:
    """Register a doctor (created PENDING) and return their user id."""
    reg = client.post("/api/v1/auth/doctor/register", json=_DOCTOR)
    assert reg.status_code == 201, reg.text
    return int(reg.json()["id"])


def _seed_admin(db: sessionmaker[Session]) -> tuple[int, str]:
    """Insert an ADMIN user directly and mint an access token for them."""
    with db() as session:
        admin = User(
            email="admin@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    token = security.create_access_token(admin_id, UserRole.ADMIN)
    return admin_id, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_patient_and_doctor_are_forbidden(client: TestClient, db: sessionmaker[Session]) -> None:
    # A DOCTOR (non-admin) token must be rejected on every admin route.
    doctor_id = _register_pending_doctor(client)
    doctor_token = security.create_access_token(doctor_id, UserRole.DOCTOR)
    # A PATIENT token likewise.
    with db() as session:
        patient = User(
            email="patient@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_token = security.create_access_token(int(patient.id), UserRole.PATIENT)

    for token in (doctor_token, patient_token):
        assert client.get("/api/v1/admin/professionals", headers=_auth(token)).status_code == 403
        assert (
            client.post(
                f"/api/v1/admin/professionals/{doctor_id}/accredit", headers=_auth(token)
            ).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/admin/professionals/{doctor_id}/revoke", headers=_auth(token)
            ).status_code
            == 403
        )


def test_admin_lists_pending_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id = _register_pending_doctor(client)
    _admin_id, token = _seed_admin(db)

    resp = client.get("/api/v1/admin/professionals?pending=true", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    listed = resp.json()
    ids = {row["user_id"] for row in listed}
    assert doctor_id in ids
    row = next(r for r in listed if r["user_id"] == doctor_id)
    assert row["license_no"] == _DOCTOR["license_no"]
    assert row["email"] == _DOCTOR["email"]


def test_admin_accredits_doctor(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id = _register_pending_doctor(client)
    _admin_id, token = _seed_admin(db)

    assert AdminController.is_doctor_verified(doctor_id) is False

    resp = client.post(f"/api/v1/admin/professionals/{doctor_id}/accredit", headers=_auth(token))
    assert resp.status_code == 200, resp.text
    assert AdminController.is_doctor_verified(doctor_id) is True

    # An accredited doctor no longer appears in the pending queue.
    listed = client.get("/api/v1/admin/professionals", headers=_auth(token)).json()
    assert doctor_id not in {row["user_id"] for row in listed}


def test_accredit_unknown_user_is_not_found(client: TestClient, db: sessionmaker[Session]) -> None:
    _admin_id, token = _seed_admin(db)
    resp = client.post("/api/v1/admin/professionals/999999/accredit", headers=_auth(token))
    assert resp.status_code == 404, resp.text
