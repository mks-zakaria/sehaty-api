"""Prescription-template API integration tests over the in-memory SQLite fixture.

These routes are non-geo (a doctor's reusable prescription presets), so they run
on the ``client``/``db`` fixtures without PostGIS — the shared conftest builds
the ``prescription_templates`` table. Flow under test: a doctor POSTs a template
and it comes back with its items; a GET lists it; a DELETE removes it; invalid
bodies (empty name / missing drug_name) are rejected (400/422); and a non-doctor
(patient/admin) is 403.
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
            "email": f"tpl-doc-{suffix}@clinic.ma",
            "password": "tpl-pw-123",
            "full_name": f"Dr Template {suffix}",
            "slug": f"dr-template-{suffix}",
            "license_no": f"LIC-TPL-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"tpl-doc-{suffix}@clinic.ma", "password": "tpl-pw-123"},
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


def _seed_admin(db: sessionmaker[Session], email: str = "tpl-admin@sehaty.ma") -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def test_create_then_list_then_delete(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "1")

    # POST a template -> 201 with its items resolved.
    created = client.post(
        "/api/v1/doctor/prescription-templates",
        headers=_auth(doctor_token),
        json={
            "name": "Angine - adulte",
            "notes": "Repos + hydratation",
            "items": [
                {
                    "drug_name": "Amoxicilline",
                    "dosage": "1g",
                    "frequency": "2x/jour",
                    "duration_days": 7,
                    "instructions": "Apres les repas",
                },
                {"drug_name": "Paracetamol", "dosage": "1g", "frequency": "si fievre"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    template_id = body["id"]
    assert body["name"] == "Angine - adulte"
    assert body["notes"] == "Repos + hydratation"
    assert len(body["items"]) == 2
    assert body["items"][0]["drug_name"] == "Amoxicilline"
    assert body["items"][0]["duration_days"] == 7
    assert body["items"][1]["duration_days"] is None

    # GET lists it (with its items).
    listing = client.get("/api/v1/doctor/prescription-templates", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert [r["id"] for r in rows] == [template_id]
    assert len(rows[0]["items"]) == 2

    # DELETE removes it -> 204, and the list is empty afterwards.
    deleted = client.delete(
        f"/api/v1/doctor/prescription-templates/{template_id}", headers=_auth(doctor_token)
    )
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    empty = client.get("/api/v1/doctor/prescription-templates", headers=_auth(doctor_token))
    assert empty.status_code == 200, empty.text
    assert empty.json() == []


def test_delete_unknown_is_404(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "2")
    resp = client.delete("/api/v1/doctor/prescription-templates/9999", headers=_auth(doctor_token))
    assert resp.status_code == 404, resp.text


def test_validation_errors_rejected(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "3")

    # Empty name -> core SehatyValidationError -> 422.
    empty_name = client.post(
        "/api/v1/doctor/prescription-templates",
        headers=_auth(doctor_token),
        json={
            "name": "   ",
            "items": [{"drug_name": "Amoxicilline", "dosage": "1g", "frequency": "2x/jour"}],
        },
    )
    assert empty_name.status_code in (400, 422), empty_name.text

    # Missing drug_name -> pydantic 422 (required field).
    missing_drug = client.post(
        "/api/v1/doctor/prescription-templates",
        headers=_auth(doctor_token),
        json={"name": "Bad", "items": [{"dosage": "1g", "frequency": "2x/jour"}]},
    )
    assert missing_drug.status_code in (400, 422), missing_drug.text


def test_non_doctor_forbidden(client: TestClient, db: sessionmaker[Session]) -> None:
    patient_token = _seed_patient(db, "tpl-patient@sehaty.ma")
    admin_token = _seed_admin(db)
    for token in (patient_token, admin_token):
        resp = client.get("/api/v1/doctor/prescription-templates", headers=_auth(token))
        assert resp.status_code == 403, resp.text
