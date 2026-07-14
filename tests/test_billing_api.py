"""Cash-billing API integration tests over a TestClient with in-memory SQLite.

The billing surface is non-geo — plans, subscriptions, invoices and cash
payments are keyed by numeric ids — so it runs on the in-memory SQLite
``client``/``db`` fixtures. Covers: the seeded plan catalogue (3 plans); a
doctor subscribing then seeing an ACTIVE plan on ``GET /me``; an admin recording
cash against an invoice (method CASH, invoice PAID) with replay idempotency on
the receipt number; and role gating (a non-admin on an admin route -> 403).
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.billing import BillingController
from sehaty.db import InvoiceStatus, User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_DOCTOR = {
    "email": "bill-doc@clinic.ma",
    "password": "bill-pw-123",
    "full_name": "Dr Billing",
    "slug": "dr-billing",
    "license_no": "LIC-BILL-1",
    "phone": "+212600001234",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient) -> tuple[int, str]:
    reg = client.post("/api/v1/auth/doctor/register", json=_DOCTOR)
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": _DOCTOR["email"], "password": _DOCTOR["password"]},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def _seed_admin(db: sessionmaker[Session], email: str = "bill-admin@sehaty.ma") -> tuple[int, str]:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return admin_id, security.create_access_token(admin_id, UserRole.ADMIN)


def _seed_patient(db: sessionmaker[Session], email: str = "bill-patient@sehaty.ma") -> str:
    with db() as session:
        patient = User(email=email, role=UserRole.PATIENT, is_active=True, password_hash="unused")
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return security.create_access_token(patient_id, UserRole.PATIENT)


def test_seed_then_list_plans(client: TestClient, db: sessionmaker[Session]) -> None:
    _admin_id, admin_token = _seed_admin(db)

    seed = client.post("/api/v1/billing/admin/seed-plans", headers=_auth(admin_token))
    assert seed.status_code == 200, seed.text
    assert seed.json()["created"] == 3

    # Seeding is idempotent: a second call creates nothing.
    reseed = client.post("/api/v1/billing/admin/seed-plans", headers=_auth(admin_token))
    assert reseed.status_code == 200, reseed.text
    assert reseed.json()["created"] == 0

    # Any authenticated user may read the catalogue.
    doctor_id, doctor_token = _register_and_login_doctor(client)
    plans = client.get("/api/v1/billing/plans", headers=_auth(doctor_token))
    assert plans.status_code == 200, plans.text
    body = plans.json()
    assert len(body) == 3
    codes = {p["code"] for p in body}
    assert codes == {"essentiel", "pro", "premium"}
    assert all(p["currency"] == "MAD" for p in body)


def test_doctor_subscribe_then_me(client: TestClient, db: sessionmaker[Session]) -> None:
    _admin_id, admin_token = _seed_admin(db)
    client.post("/api/v1/billing/admin/seed-plans", headers=_auth(admin_token))
    _doctor_id, doctor_token = _register_and_login_doctor(client)

    sub = client.post(
        "/api/v1/billing/me/subscribe",
        headers=_auth(doctor_token),
        json={"plan_code": "pro"},
    )
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "ACTIVE"

    me = client.get("/api/v1/billing/me", headers=_auth(doctor_token))
    assert me.status_code == 200, me.text
    summary = me.json()
    assert summary["plan"] == "pro"
    assert summary["status"] == "ACTIVE"


def test_admin_records_cash_payment_is_idempotent(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    admin_id, admin_token = _seed_admin(db)
    client.post("/api/v1/billing/admin/seed-plans", headers=_auth(admin_token))
    doctor_id, doctor_token = _register_and_login_doctor(client)

    # Subscribe and issue an OPEN invoice for the period (via core).
    client.post(
        "/api/v1/billing/me/subscribe",
        headers=_auth(doctor_token),
        json={"plan_code": "essentiel"},
    )
    invoice = BillingController.generate_invoice(doctor_id)
    invoice_id = int(invoice.id)

    pay = client.post(
        "/api/v1/billing/admin/payments",
        headers=_auth(admin_token),
        json={"invoice_id": invoice_id, "amount": 199.0, "receipt_no": "R-0001"},
    )
    assert pay.status_code == 200, pay.text
    first = pay.json()
    assert first["method"] == "CASH"
    assert first["invoice_id"] == invoice_id

    with db() as session:
        from sehaty.db import Invoice

        assert session.get(Invoice, invoice_id).status == InvoiceStatus.PAID

    # Replaying the same receipt returns the same payment; invoice stays PAID.
    replay = client.post(
        "/api/v1/billing/admin/payments",
        headers=_auth(admin_token),
        json={"invoice_id": invoice_id, "amount": 199.0, "receipt_no": "R-0001"},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["id"] == first["id"]

    with db() as session:
        from sehaty.db import Invoice, Payment

        assert session.get(Invoice, invoice_id).status == InvoiceStatus.PAID
        payments = session.query(Payment).filter(Payment.invoice_id == invoice_id).all()
        assert len(payments) == 1


def test_non_admin_hitting_admin_endpoint_is_403(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _doctor_id, doctor_token = _register_and_login_doctor(client)
    patient_token = _seed_patient(db)

    for token in (doctor_token, patient_token):
        seed = client.post("/api/v1/billing/admin/seed-plans", headers=_auth(token))
        assert seed.status_code == 403, seed.text
        dunning = client.post("/api/v1/billing/admin/dunning", headers=_auth(token))
        assert dunning.status_code == 403, dunning.text
        payment = client.post(
            "/api/v1/billing/admin/payments",
            headers=_auth(token),
            json={"invoice_id": 1, "amount": 10.0, "receipt_no": "R-X"},
        )
        assert payment.status_code == 403, payment.text
