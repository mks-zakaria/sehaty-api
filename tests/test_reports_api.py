"""Admin reporting API integration tests over a TestClient with in-memory SQLite.

The reporting surface is read-only aggregation over the whole schema; the shared
``db``/``client`` fixtures already build every table the ``ReportingController``
reads (users, doctor_profiles, appointments, reviews, referrals, plans,
subscriptions, invoices, payments, credit_ledger) and register the PostGIS
``Geography -> TEXT`` shim, so it runs on the in-memory SQLite engine. A tiny
fixture (a verified doctor, a patient, an active subscription, one invoice + one
CASH payment this year) is seeded directly via the session factory. Covers: the
admin KPI snapshot; the fiscal-year revenue summary (cash total); the CSV
accounting export (media type + header + invoice/payment rows); and role gating
(a non-admin on any reports route -> 403).
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import (
    DoctorProfile,
    Invoice,
    InvoiceStatus,
    Payment,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy.orm import Session, sessionmaker

_YEAR = datetime.now(UTC).year


def _dt(month: int, day: int = 15, *, year: int = _YEAR) -> datetime:
    return datetime(year, month, day, 10, 0, tzinfo=UTC)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: sessionmaker[Session], email: str = "rep-admin@sehaty.ma") -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _seed_patient_token(db: sessionmaker[Session]) -> str:
    with db() as session:
        patient = User(
            email="rep-patient2@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return security.create_access_token(patient_id, UserRole.PATIENT)


def _seed_fixture(db: sessionmaker[Session]) -> dict[str, int]:
    """A verified doctor, a patient, an active subscription, one invoice + CASH payment."""
    ids: dict[str, int] = {}
    with db() as s:
        doctor = User(email="rep-doc@clinic.ma", role=UserRole.DOCTOR, is_active=True)
        patient = User(email="rep-pat@sehaty.ma", role=UserRole.PATIENT, is_active=True)
        s.add_all([doctor, patient])
        s.flush()
        ids.update(doctor=int(doctor.id), patient=int(patient.id))

        s.add(
            DoctorProfile(
                user_id=doctor.id,
                full_name="Dr Reporting",
                slug="dr-reporting",
                license_no="LIC-REP-1",
                verification_status=VerificationStatus.VERIFIED,
            )
        )

        plan = Plan(code="essentiel", name="Essentiel", price_month=199.0, currency="MAD")
        s.add(plan)
        s.flush()
        s.add(
            Subscription(
                doctor_id=doctor.id,
                plan_id=plan.id,
                status=SubscriptionStatus.ACTIVE,
                current_period_start=_dt(1),
                current_period_end=_dt(2),
            )
        )

        invoice = Invoice(
            doctor_id=doctor.id,
            amount=199.0,
            currency="MAD",
            status=InvoiceStatus.PAID,
            issued_at=_dt(2),
            due_at=_dt(3),
            paid_at=_dt(2),
        )
        s.add(invoice)
        s.flush()
        ids["invoice"] = int(invoice.id)

        s.add(
            Payment(
                invoice_id=invoice.id,
                amount=199.0,
                method="CASH",
                provider_ref="R-REP-1",
                paid_at=_dt(2),
            )
        )
        s.commit()
    return ids


def test_admin_kpis(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed_fixture(db)
    admin_token = _seed_admin(db)

    resp = client.get("/api/v1/admin/reports/kpis", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["doctors_total"] == 1
    assert body["doctors_verified"] == 1
    assert body["patients_total"] == 1
    assert body["active_subscriptions"] == 1


def test_admin_revenue(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed_fixture(db)
    admin_token = _seed_admin(db)

    resp = client.get(
        "/api/v1/admin/reports/revenue",
        params={"year": _YEAR},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["year"] == _YEAR
    assert body["currency"] == "MAD"
    assert body["total_collected"] == 199.0
    assert body["mrr"] == 199.0
    assert [(m["month"], m["collected"], m["payments"]) for m in body["by_month"]] == [
        (2, 199.0, 1)
    ]


def test_admin_accounting_export_csv(client: TestClient, db: sessionmaker[Session]) -> None:
    ids = _seed_fixture(db)
    admin_token = _seed_admin(db)

    resp = client.get(
        "/api/v1/admin/reports/accounting-export",
        params={"year": _YEAR},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert (
        resp.headers["content-disposition"]
        == f'attachment; filename="sehaty-accounting-{_YEAR}.csv"'
    )

    lines = [line for line in resp.text.splitlines() if line]
    assert lines[0] == "date,kind,reference,doctor_id,amount,currency,detail"
    body = resp.text
    # The seeded invoice row (reference = invoice id) and the CASH payment row.
    assert f",INVOICE,{ids['invoice']}," in body
    assert ",PAYMENT,R-REP-1," in body
    # header + invoice + payment.
    assert len(lines) >= 3


def test_non_admin_hitting_reports_is_403(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed_fixture(db)
    patient_token = _seed_patient_token(db)

    for path in ("/kpis", "/revenue", "/accounting-export"):
        resp = client.get(f"/api/v1/admin/reports{path}", headers=_auth(patient_token))
        assert resp.status_code == 403, resp.text
