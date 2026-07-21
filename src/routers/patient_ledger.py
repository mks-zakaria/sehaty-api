"""Patient debt-ledger router. Body of each handler: parse -> ONE controller
call -> return.

No SQLAlchemy here. A doctor records a treatment charge (e.g. braces paid in
instalments) against one of their register patients and collects payments
against it over time; the outstanding balance is always derived server-side.
Every route is DOCTOR-scoped: the caller's own user id is the ``doctor_id`` (and
``created_by``), so a charge/patient belonging to another doctor is a 404.
Business errors (``SehatyNotFoundError`` -> 404, ``SehatyValidationError`` ->
400) are mapped to HTTP by the global exception handler in ``main``.
"""

from fastapi import APIRouter, Depends, status
from sehaty.core.controllers.patient_ledger import (
    ChargeRow,
    DebtorRow,
    MyDebtsSummary,
    PatientLedgerController,
    PatientLedgerSummary,
)
from sehaty.db import User, UserRole

from deps import require_roles
from schemas.patient_ledger import ChargeCreateIn, PaymentCreateIn

router = APIRouter(prefix="/api/v1/doctor", tags=["patient-ledger"])

# Patient-facing view of one's own charges (separate prefix + role).
me_router = APIRouter(prefix="/api/v1/me", tags=["patient-ledger"])

_require_doctor = require_roles(UserRole.DOCTOR)
_require_patient = require_roles(UserRole.PATIENT)


@me_router.get("/ledger", response_model=MyDebtsSummary)
def my_ledger(patient: User = Depends(_require_patient)) -> MyDebtsSummary:
    """The signed-in patient's charges across every doctor, with the total due."""
    return PatientLedgerController.my_debts(patient.id)


@router.get("/patients/{patient_id}/ledger", response_model=PatientLedgerSummary)
def get_ledger(
    patient_id: int,
    doctor: User = Depends(_require_doctor),
) -> PatientLedgerSummary:
    """The patient's charges (newest first) with rolled-up totals (404 if not the doctor's)."""
    return PatientLedgerController.list_charges(doctor.id, patient_id)


@router.post(
    "/patients/{patient_id}/ledger/charges",
    response_model=ChargeRow,
    status_code=status.HTTP_201_CREATED,
)
def add_charge(
    patient_id: int,
    body: ChargeCreateIn,
    doctor: User = Depends(_require_doctor),
) -> ChargeRow:
    """Record a treatment charge, optionally with a same-visit down payment."""
    return PatientLedgerController.add_charge(
        doctor_id=doctor.id,
        patient_id=patient_id,
        created_by=doctor.id,
        label=body.label,
        total_amount=body.total_amount,
        currency=body.currency,
        note=body.note,
        initial_payment=body.initial_payment,
    )


@router.post("/ledger/charges/{charge_id}/payments", response_model=ChargeRow)
def add_payment(
    charge_id: int,
    body: PaymentCreateIn,
    doctor: User = Depends(_require_doctor),
) -> ChargeRow:
    """Record an instalment (400 over the balance) and return the updated charge."""
    return PatientLedgerController.add_payment(
        doctor_id=doctor.id,
        charge_id=charge_id,
        created_by=doctor.id,
        amount=body.amount,
        method=body.method,
        note=body.note,
        paid_at=body.paid_at,
    )


@router.delete("/ledger/charges/{charge_id}/payments/{payment_id}", response_model=ChargeRow)
def delete_payment(
    charge_id: int,
    payment_id: int,
    doctor: User = Depends(_require_doctor),
) -> ChargeRow:
    """Remove a mis-entered payment and return the updated charge."""
    return PatientLedgerController.delete_payment(doctor.id, charge_id, payment_id)


@router.delete("/ledger/charges/{charge_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_charge(
    charge_id: int,
    doctor: User = Depends(_require_doctor),
) -> None:
    """Remove a mis-entered charge and, by cascade, its payments."""
    PatientLedgerController.delete_charge(doctor.id, charge_id)


@router.get("/ledger/debtors", response_model=list[DebtorRow])
def list_debtors(
    limit: int = 100,
    doctor: User = Depends(_require_doctor),
) -> list[DebtorRow]:
    """Register patients who still owe money, biggest balance first."""
    return PatientLedgerController.list_debtors(doctor.id, limit=limit)
