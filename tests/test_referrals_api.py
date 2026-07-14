"""Referral API integration tests over a TestClient with in-memory SQLite.

The referral surface is non-geo — codes, referrals and the credit ledger are
keyed by numeric ids — so it runs on the in-memory SQLite ``client``/``db``
fixtures. Covers: a doctor's referral code being non-empty and stable across
calls; a new doctor registering with a referrer's code showing up as that
referrer's one referral (record_referral applied); registration with an unknown
code still succeeding with no referral created; and a fresh doctor's credit
balance being 0.0 before any reward.
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

_DOCTOR_A = {
    "email": "ref-a@clinic.ma",
    "password": "ref-pw-a-123",
    "full_name": "Dr Referrer",
    "slug": "dr-referrer",
    "license_no": "LIC-REF-A",
    "phone": "+212600002001",
}
_DOCTOR_B = {
    "email": "ref-b@clinic.ma",
    "password": "ref-pw-b-123",
    "full_name": "Dr Referred",
    "slug": "dr-referred",
    "license_no": "LIC-REF-B",
    "phone": "+212600002002",
}


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_and_login_doctor(client: TestClient, doctor: dict) -> tuple[int, str]:
    reg = client.post("/api/v1/auth/doctor/register", json=doctor)
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": doctor["email"], "password": doctor["password"]},
    )
    assert login.status_code == 200, login.text
    return doctor_id, login.json()["access"]


def test_my_code_is_non_empty_and_stable(client: TestClient, db: sessionmaker[Session]) -> None:
    _doctor_id, token = _register_and_login_doctor(client, _DOCTOR_A)

    first = client.get("/api/v1/referrals/me/code", headers=_auth(token))
    assert first.status_code == 200, first.text
    code = first.json()["code"]
    assert code

    # A second read returns the same, persisted code.
    second = client.get("/api/v1/referrals/me/code", headers=_auth(token))
    assert second.status_code == 200, second.text
    assert second.json()["code"] == code


def test_register_with_referral_code_records_referral(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_a_id, token_a = _register_and_login_doctor(client, _DOCTOR_A)
    code = client.get("/api/v1/referrals/me/code", headers=_auth(token_a)).json()["code"]

    reg_b = client.post(
        "/api/v1/auth/doctor/register",
        json={**_DOCTOR_B, "referral_code": code},
    )
    assert reg_b.status_code == 201, reg_b.text
    doctor_b_id = int(reg_b.json()["id"])

    me = client.get("/api/v1/referrals/me", headers=_auth(token_a))
    assert me.status_code == 200, me.text
    body = me.json()
    assert len(body["referrals"]) == 1
    referral = body["referrals"][0]
    assert referral["referred_doctor_id"] == doctor_b_id
    assert referral["status"] == "PENDING"


def test_register_with_unknown_code_still_succeeds(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor_a_id, token_a = _register_and_login_doctor(client, _DOCTOR_A)

    reg_b = client.post(
        "/api/v1/auth/doctor/register",
        json={**_DOCTOR_B, "referral_code": "NOSUCHCODE"},
    )
    assert reg_b.status_code == 201, reg_b.text

    # No referral was created for doctor A off an unknown code.
    me = client.get("/api/v1/referrals/me", headers=_auth(token_a))
    assert me.status_code == 200, me.text
    assert me.json()["referrals"] == []


def test_credit_balance_is_zero_before_reward(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _doctor_id, token = _register_and_login_doctor(client, _DOCTOR_A)

    me = client.get("/api/v1/referrals/me", headers=_auth(token))
    assert me.status_code == 200, me.text
    assert me.json()["credit_balance"] == 0.0
