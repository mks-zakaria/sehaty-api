"""Pharmacy dispensing API integration test (in-memory SQLite fixture).

Registers a pharmacy, seeds a doctor's prescription with two lines, then looks it
up by code and dispenses part of it over HTTP.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sehaty.db import (
    Medication,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    User,
    UserRole,
)
from sqlalchemy.orm import Session, sessionmaker

_NOW = datetime(2026, 8, 3, 9, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_pharmacy(client: TestClient) -> str:
    reg = client.post(
        "/api/v1/auth/pharmacy/register",
        json={"email": "pharma@sehaty.ma", "password": "pharma-pw-123"},
    )
    assert reg.status_code == 201, reg.text
    assert reg.json()["role"] == "PHARMACY"
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "pharma@sehaty.ma", "password": "pharma-pw-123"},
    )
    return login.json()["access"]


def _seed_prescription(db: sessionmaker[Session]) -> tuple[str, int]:
    with db() as s:
        doctor = User(email="rxdoc@clinic.ma", role=UserRole.DOCTOR, is_active=True)
        s.add(doctor)
        s.flush()
        rx = Prescription(
            doctor_id=doctor.id, code="RX-API-1", qr_token="tok-api-1",
            status=PrescriptionStatus.ISSUED, issued_at=_NOW,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        s.add(rx)
        s.flush()
        item = PrescriptionItem(
            prescription_id=rx.id, drug_name="Amoxicillin", dosage="1 tab",
            frequency="2x/day", quantity=10,
        )
        s.add(item)
        s.commit()
        return rx.code, item.id


def test_pharmacy_lookup_and_dispense(client: TestClient, db: sessionmaker[Session]) -> None:
    token = _register_pharmacy(client)
    h = _auth(token)
    code, item_id = _seed_prescription(db)

    # Look up the prescription by code.
    view = client.get(f"/api/v1/pharmacy/prescriptions/{code}", headers=h)
    assert view.status_code == 200, view.text
    body = view.json()
    assert body["code"] == code and body["fully_dispensed"] is False
    assert body["items"][0]["remaining"] == 10

    # Dispense part of it.
    disp = client.post(
        "/api/v1/pharmacy/dispenses",
        json={"code": code, "lines": [{"prescription_item_id": item_id, "quantity": 4}]},
        headers=h,
    )
    assert disp.status_code == 200, disp.text
    assert disp.json()["items"][0]["quantity"] == 4

    # Outstanding amount dropped.
    again = client.get(f"/api/v1/pharmacy/prescriptions/{code}", headers=h).json()
    assert again["items"][0]["quantity_dispensed"] == 4
    assert again["items"][0]["remaining"] == 6

    # Over-dispensing the rest+1 is a 409.
    over = client.post(
        "/api/v1/pharmacy/dispenses",
        json={"code": code, "lines": [{"prescription_item_id": item_id, "quantity": 7}]},
        headers=h,
    )
    assert over.status_code == 409, over.text


def test_pharmacy_stock_management(client: TestClient, db: sessionmaker[Session]) -> None:
    token = _register_pharmacy(client)
    h = _auth(token)
    with db() as s:
        med = Medication(inn_name="Ibuprofen", form="tablet")
        s.add(med)
        s.commit()
        med_id = med.id

    assert client.get("/api/v1/pharmacy/stock", headers=h).json() == []

    saved = client.post(
        "/api/v1/pharmacy/stock",
        json={"medication_id": med_id, "quantity": 3, "low_threshold": 5},
        headers=h,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["is_low"] is True

    listed = client.get("/api/v1/pharmacy/stock", headers=h).json()
    assert len(listed) == 1 and listed[0]["medication"] == "Ibuprofen"
    assert len(client.get("/api/v1/pharmacy/stock?low=true", headers=h).json()) == 1

    meds = client.get("/api/v1/pharmacy/medications?q=ibu", headers=h).json()
    assert any(m["id"] == med_id for m in meds)


def test_pharmacy_endpoints_require_auth(client: TestClient) -> None:
    # No token -> 401.
    assert client.get("/api/v1/pharmacy/prescriptions/ANY").status_code == 401
