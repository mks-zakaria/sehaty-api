"""Patient debt-ledger API integration tests over the in-memory SQLite fixture.

Non-geo routes (the doctor-scoped treatment ledger), so they run on the
`client`/`db` fixtures without PostGIS. Flow under test: the doctor adds a
walk-in register patient, records a charge with a down payment, the ledger
derives the balance, instalments accumulate (overpayment is a 400), a
mis-entered payment is deleted, the practice-wide debtors roll-up ranks by
balance, a foreign doctor's rows are 404, and a PATIENT token is 403.
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
            "email": f"led-doc-{suffix}@clinic.ma",
            "password": "led-pw-123",
            "full_name": f"Dr Ledger {suffix}",
            "slug": f"dr-ledger-{suffix}",
            "license_no": f"LIC-LED-{suffix}",
            "phone": f"+21261400{suffix:0>4}",
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": f"led-doc-{suffix}@clinic.ma", "password": "led-pw-123"},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _add_walkin(client: TestClient, token: str, name: str) -> int:
    resp = client.post("/api/v1/doctor/patients", headers=_auth(token), json={"full_name": name})
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


def _patient_token(db: sessionmaker[Session]) -> str:
    with db() as session:
        patient = User(
            email="led-pat@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return security.create_access_token(patient_id, UserRole.PATIENT)


def test_charge_instalments_and_balance(client: TestClient) -> None:
    _, token = _register_and_login_doctor(client, "1")
    patient_id = _add_walkin(client, token, "Braces Patient")

    resp = client.post(
        f"/api/v1/doctor/patients/{patient_id}/ledger/charges",
        headers=_auth(token),
        json={"label": "Braces", "total_amount": 8000, "initial_payment": 3000},
    )
    assert resp.status_code == 201, resp.text
    charge = resp.json()
    assert charge["balance"] == 5000
    assert len(charge["payments"]) == 1

    resp = client.post(
        f"/api/v1/doctor/ledger/charges/{charge['id']}/payments",
        headers=_auth(token),
        json={"amount": 2500, "method": "CARD"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["balance"] == 2500

    # Overpaying the remaining balance is a validation error (400).
    resp = client.post(
        f"/api/v1/doctor/ledger/charges/{charge['id']}/payments",
        headers=_auth(token),
        json={"amount": 9999},
    )
    assert resp.status_code == 400, resp.text

    ledger = client.get(f"/api/v1/doctor/patients/{patient_id}/ledger", headers=_auth(token))
    assert ledger.status_code == 200, ledger.text
    body = ledger.json()
    assert body["total_charged"] == 8000
    assert body["total_paid"] == 5500
    assert body["total_outstanding"] == 2500


def test_payment_correction_and_debtors(client: TestClient) -> None:
    _, token = _register_and_login_doctor(client, "2")
    big = _add_walkin(client, token, "Big Debt")
    small = _add_walkin(client, token, "Small Debt")

    charge = client.post(
        f"/api/v1/doctor/patients/{big}/ledger/charges",
        headers=_auth(token),
        json={"label": "Braces", "total_amount": 8000, "initial_payment": 2000},
    ).json()
    client.post(
        f"/api/v1/doctor/patients/{small}/ledger/charges",
        headers=_auth(token),
        json={"label": "Cleaning", "total_amount": 400, "initial_payment": 100},
    )

    wrong = client.post(
        f"/api/v1/doctor/ledger/charges/{charge['id']}/payments",
        headers=_auth(token),
        json={"amount": 999},
    ).json()
    fixed = client.delete(
        f"/api/v1/doctor/ledger/charges/{charge['id']}/payments/{wrong['payments'][-1]['id']}",
        headers=_auth(token),
    )
    assert fixed.status_code == 200, fixed.text
    assert fixed.json()["balance"] == 6000

    debtors = client.get("/api/v1/doctor/ledger/debtors", headers=_auth(token))
    assert debtors.status_code == 200, debtors.text
    rows = debtors.json()
    assert [(r["full_name"], r["balance"]) for r in rows] == [
        ("Big Debt", 6000.0),
        ("Small Debt", 300.0),
    ]


def test_scoping_and_roles(client: TestClient, db: sessionmaker[Session]) -> None:
    _, token = _register_and_login_doctor(client, "3")
    _, other_token = _register_and_login_doctor(client, "4")
    patient_id = _add_walkin(client, token, "Scoped Patient")
    charge = client.post(
        f"/api/v1/doctor/patients/{patient_id}/ledger/charges",
        headers=_auth(token),
        json={"label": "Braces", "total_amount": 1000},
    ).json()

    # Another doctor cannot see or touch this ledger.
    assert (
        client.get(
            f"/api/v1/doctor/patients/{patient_id}/ledger", headers=_auth(other_token)
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/doctor/ledger/charges/{charge['id']}", headers=_auth(other_token)
        ).status_code
        == 404
    )

    # A PATIENT token is rejected outright.
    patient_token = _patient_token(db)
    assert (
        client.get("/api/v1/doctor/ledger/debtors", headers=_auth(patient_token)).status_code == 403
    )

    # The owner can delete the charge (payments cascade).
    assert (
        client.delete(
            f"/api/v1/doctor/ledger/charges/{charge['id']}", headers=_auth(token)
        ).status_code
        == 204
    )
    ledger = client.get(f"/api/v1/doctor/patients/{patient_id}/ledger", headers=_auth(token))
    assert ledger.json()["charges"] == []


def test_my_ledger_patient_view(client: TestClient, db: sessionmaker[Session]) -> None:
    """A patient sees their own charges via /api/v1/me/ledger; roles are enforced."""
    from sehaty.db import ClinicPatient

    doctor_id, token = _register_and_login_doctor(client, "9")
    # Registration already created the doctor_profiles row (full_name "Dr Ledger 9");
    # just link a patient account to this doctor's register.
    with db() as s:
        patient = User(
            email="me-pat@app.ma", role=UserRole.PATIENT, is_active=True, password_hash="unused"
        )
        s.add(patient)
        s.commit()
        patient_id = int(patient.id)
        cp = ClinicPatient(doctor_id=doctor_id, user_id=patient_id, full_name="Me Patient")
        s.add(cp)
        s.commit()
        clinic_patient_id = int(cp.id)

    # Doctor bills the linked register row.
    resp = client.post(
        f"/api/v1/doctor/patients/{clinic_patient_id}/ledger/charges",
        headers=_auth(token),
        json={"label": "Braces", "total_amount": 8000, "initial_payment": 3000},
    )
    assert resp.status_code == 201, resp.text

    patient_token = security.create_access_token(patient_id, UserRole.PATIENT)
    me = client.get("/api/v1/me/ledger", headers=_auth(patient_token))
    assert me.status_code == 200, me.text
    body = me.json()
    assert body["total_outstanding"] == 5000
    assert len(body["charges"]) == 1
    assert body["charges"][0]["label"] == "Braces"
    assert body["charges"][0]["doctor_name"] == "Dr Ledger 9"
    assert body["charges"][0]["balance"] == 5000

    # A doctor token is rejected on the patient endpoint.
    assert client.get("/api/v1/me/ledger", headers=_auth(token)).status_code == 403
