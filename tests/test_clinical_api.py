"""Clinical-workspace API integration tests over the in-memory SQLite fixture.

These routes are non-geo (doctor-scoped clinical records + patient-scoped
``/me`` reads), so they run on the shared ``client``/``db`` fixtures without
PostGIS — conftest builds the ``practice_profiles`` / ``prescriptions`` /
``prescription_items`` / ``diagnoses`` / ``treatment_feedback`` / ``medications``
tables alongside the register + appointment tables. Flow under test: a doctor
creates a letterhead (the first is default), prescribes + diagnoses for a
walk-in, and cancels a prescription; an app patient (whose booking linked their
register row by ``user_id``) reads their own prescriptions/diagnoses and leaves
feedback on their own diagnosis; feedback on someone else's record is 403; and
role gates hold (non-doctor -> 403 on doctor routes, non-patient -> 403 on
``/me/*``).
"""

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_TARGET_DAY: date = date.today() + timedelta(days=7)


def _slot(hour: int, minute: int) -> datetime:
    return datetime(_TARGET_DAY.year, _TARGET_DAY.month, _TARGET_DAY.day, hour, minute, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, suffix: str) -> tuple[int, str]:
    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": f"clin-doc-{suffix}@clinic.ma",
            "password": "clin-pw-123",
            "full_name": f"Dr Clinical {suffix}",
            "slug": f"dr-clinical-{suffix}",
            "license_no": f"LIC-CLIN-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"clin-doc-{suffix}@clinic.ma", "password": "clin-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_patient(db: sessionmaker[Session], email: str) -> tuple[int, str]:
    with db() as session:
        patient = User(email=email, role=UserRole.PATIENT, is_active=True, password_hash="unused")
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return patient_id, security.create_access_token(patient_id, UserRole.PATIENT)


def _seed_admin(db: sessionmaker[Session], email: str = "clin-admin@sehaty.ma") -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _add_window(client: TestClient, token: str) -> None:
    resp = client.post(
        "/api/v1/doctors/me/availability",
        headers=_auth(token),
        json={
            "weekday": _TARGET_DAY.weekday(),
            "start_time": "09:00",
            "end_time": "12:00",
            "slot_minutes": 30,
        },
    )
    assert resp.status_code == 201, resp.text


def _book(client: TestClient, patient_token: str, doctor_id: int, start_at: datetime) -> None:
    book = client.post(
        "/api/v1/appointments",
        headers=_auth(patient_token),
        json={"doctor_id": doctor_id, "start_at": start_at.isoformat(), "reason": "Checkup"},
    )
    assert book.status_code == 201, book.text


def _register_row_id(client: TestClient, doctor_token: str, user_id: int) -> int:
    listing = client.get("/api/v1/doctor/patients", headers=_auth(doctor_token))
    assert listing.status_code == 200, listing.text
    for row in listing.json():
        if row["user_id"] == user_id:
            return int(row["id"])
    raise AssertionError(f"no register row for user {user_id}")


def _add_walkin(client: TestClient, doctor_token: str, name: str) -> int:
    created = client.post(
        "/api/v1/doctor/patients",
        headers=_auth(doctor_token),
        json={"full_name": name},
    )
    assert created.status_code == 201, created.text
    return int(created.json()["id"])


# --- Doctor workspace --------------------------------------------------------


def test_doctor_letterhead_prescription_and_diagnosis_flow(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "1")

    # First practice profile is forced default.
    created = client.post(
        "/api/v1/doctor/practice-profiles",
        headers=_auth(doctor_token),
        json={"name": "Cabinet Zerktouni", "clinic_name": "Clinique Al Amal", "city": "Casablanca"},
    )
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["is_default"] is True
    assert profile["name"] == "Cabinet Zerktouni"

    profiles = client.get("/api/v1/doctor/practice-profiles", headers=_auth(doctor_token))
    assert profiles.status_code == 200, profiles.text
    assert [p["id"] for p in profiles.json()] == [profile["id"]]

    # Walk-in patient + a freehand prescription.
    patient_id = _add_walkin(client, doctor_token, "Walk In Karim")
    rx = client.post(
        f"/api/v1/doctor/patients/{patient_id}/prescriptions",
        headers=_auth(doctor_token),
        json={
            "items": [
                {
                    "drug_name": "Amoxicilline 500mg",
                    "dosage": "1 comprimé",
                    "frequency": "3x/jour",
                    "duration_days": 7,
                    "quantity": 21,
                }
            ],
            "notes": "Après les repas",
        },
    )
    assert rx.status_code == 201, rx.text
    rx_body = rx.json()
    rx_id = rx_body["id"]
    assert rx_body["status"] == "ISSUED"
    assert len(rx_body["items"]) == 1
    assert rx_body["items"][0]["drug_name"] == "Amoxicilline 500mg"
    assert rx_body["code"]

    # List summaries for the patient.
    listing = client.get(
        f"/api/v1/doctor/patients/{patient_id}/prescriptions", headers=_auth(doctor_token)
    )
    assert listing.status_code == 200, listing.text
    assert [r["id"] for r in listing.json()] == [rx_id]
    assert listing.json()[0]["item_count"] == 1

    # Detail returns items + the letterhead snapshot.
    detail = client.get(f"/api/v1/doctor/prescriptions/{rx_id}", headers=_auth(doctor_token))
    assert detail.status_code == 200, detail.text
    dbody = detail.json()
    assert len(dbody["items"]) == 1
    assert dbody["letterhead"] is not None
    assert dbody["letterhead"]["name"] == "Cabinet Zerktouni"

    # A diagnosis for the same patient, then list.
    dx = client.post(
        f"/api/v1/doctor/patients/{patient_id}/diagnoses",
        headers=_auth(doctor_token),
        json={"label": "Angine bactérienne", "icd10": "J03.9"},
    )
    assert dx.status_code == 201, dx.text
    assert dx.json()["label"] == "Angine bactérienne"
    dx_list = client.get(
        f"/api/v1/doctor/patients/{patient_id}/diagnoses", headers=_auth(doctor_token)
    )
    assert dx_list.status_code == 200, dx_list.text
    assert [d["id"] for d in dx_list.json()] == [dx.json()["id"]]

    # Cancel the prescription.
    cancelled = client.post(
        f"/api/v1/doctor/prescriptions/{rx_id}/cancel", headers=_auth(doctor_token)
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"


# --- Patient scope + feedback ------------------------------------------------


def test_patient_reads_and_feedback_ownership(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_id, doctor_token = _register_and_login_doctor(client, "2")
    _add_window(client, doctor_token)

    # Two app patients, each booking (which links their register row by user_id).
    p1_id, p1_token = _seed_patient(db, "clin-p1@sehaty.ma")
    p2_id, p2_token = _seed_patient(db, "clin-p2@sehaty.ma")
    _book(client, p1_token, doctor_id, _slot(9, 0))
    _book(client, p2_token, doctor_id, _slot(9, 30))
    cp1 = _register_row_id(client, doctor_token, p1_id)
    _cp2 = _register_row_id(client, doctor_token, p2_id)

    # Doctor issues a prescription + diagnosis for patient 1.
    rx = client.post(
        f"/api/v1/doctor/patients/{cp1}/prescriptions",
        headers=_auth(doctor_token),
        json={"items": [{"drug_name": "Paracétamol", "dosage": "1g", "frequency": "3x/jour"}]},
    )
    assert rx.status_code == 201, rx.text
    dx1 = client.post(
        f"/api/v1/doctor/patients/{cp1}/diagnoses",
        headers=_auth(doctor_token),
        json={"label": "Grippe"},
    )
    assert dx1.status_code == 201, dx1.text
    dx1_id = dx1.json()["id"]

    # Patient 1 sees their own prescription + diagnosis.
    me_rx = client.get("/api/v1/me/prescriptions", headers=_auth(p1_token))
    assert me_rx.status_code == 200, me_rx.text
    assert [r["id"] for r in me_rx.json()] == [rx.json()["id"]]
    me_dx = client.get("/api/v1/me/diagnoses", headers=_auth(p1_token))
    assert me_dx.status_code == 200, me_dx.text
    assert [d["id"] for d in me_dx.json()] == [dx1_id]

    # Patient 2 has none of patient 1's records.
    assert client.get("/api/v1/me/diagnoses", headers=_auth(p2_token)).json() == []

    # Patient 1 leaves feedback on their OWN diagnosis -> ok.
    fb = client.post(
        "/api/v1/me/feedback",
        headers=_auth(p1_token),
        json={
            "target_type": "diagnosis",
            "target_id": dx1_id,
            "outcome": "BETTER",
            "comment": "Merci",
        },
    )
    assert fb.status_code == 201, fb.text
    assert fb.json()["outcome"] == "BETTER"

    # Patient 2 on patient 1's diagnosis -> 403.
    forbidden = client.post(
        "/api/v1/me/feedback",
        headers=_auth(p2_token),
        json={"target_type": "diagnosis", "target_id": dx1_id, "outcome": "WORSE"},
    )
    assert forbidden.status_code == 403, forbidden.text

    # Doctor sees patient 1's feedback.
    doc_fb = client.get(f"/api/v1/doctor/patients/{cp1}/feedback", headers=_auth(doctor_token))
    assert doc_fb.status_code == 200, doc_fb.text
    assert [f["id"] for f in doc_fb.json()] == [fb.json()["id"]]
    assert doc_fb.json()[0]["author_user_id"] == p1_id


def test_patient_prescription_detail_scope(client: TestClient, db: sessionmaker[Session]) -> None:
    """GET /me/prescriptions/{id}: own -> items; other patient -> 403; unknown -> 404."""
    doctor_id, doctor_token = _register_and_login_doctor(client, "5")
    _add_window(client, doctor_token)

    p1_id, p1_token = _seed_patient(db, "clin-detail-p1@sehaty.ma")
    p2_id, p2_token = _seed_patient(db, "clin-detail-p2@sehaty.ma")
    _book(client, p1_token, doctor_id, _slot(9, 0))
    _book(client, p2_token, doctor_id, _slot(9, 30))
    cp1 = _register_row_id(client, doctor_token, p1_id)

    rx = client.post(
        f"/api/v1/doctor/patients/{cp1}/prescriptions",
        headers=_auth(doctor_token),
        json={"items": [{"drug_name": "Ibuprofène", "dosage": "400mg", "frequency": "2x/jour"}]},
    )
    assert rx.status_code == 201, rx.text
    rx_id = rx.json()["id"]

    # Owner sees the full detail (items + letterhead field present).
    own = client.get(f"/api/v1/me/prescriptions/{rx_id}", headers=_auth(p1_token))
    assert own.status_code == 200, own.text
    body = own.json()
    assert body["id"] == rx_id
    assert [i["drug_name"] for i in body["items"]] == ["Ibuprofène"]
    assert "letterhead" in body

    # Another patient is forbidden.
    other = client.get(f"/api/v1/me/prescriptions/{rx_id}", headers=_auth(p2_token))
    assert other.status_code == 403, other.text

    # Unknown prescription id -> 404.
    missing = client.get("/api/v1/me/prescriptions/999999", headers=_auth(p1_token))
    assert missing.status_code == 404, missing.text


# --- Role gates --------------------------------------------------------------


def test_non_doctor_on_doctor_route_is_403(client: TestClient, db: sessionmaker[Session]) -> None:
    _, patient_token = _seed_patient(db, "clin-role-p@sehaty.ma")
    admin_token = _seed_admin(db)
    for token in (patient_token, admin_token):
        resp = client.get("/api/v1/doctor/practice-profiles", headers=_auth(token))
        assert resp.status_code == 403, resp.text


def test_non_patient_on_me_routes_is_403(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client, "3")
    admin_token = _seed_admin(db, "clin-admin2@sehaty.ma")
    for token in (doctor_token, admin_token):
        assert client.get("/api/v1/me/prescriptions", headers=_auth(token)).status_code == 403
        assert client.get("/api/v1/me/prescriptions/1", headers=_auth(token)).status_code == 403
        assert client.get("/api/v1/me/diagnoses", headers=_auth(token)).status_code == 403
        fb = client.post(
            "/api/v1/me/feedback",
            headers=_auth(token),
            json={"target_type": "diagnosis", "target_id": 1, "outcome": "BETTER"},
        )
        assert fb.status_code == 403, fb.text
