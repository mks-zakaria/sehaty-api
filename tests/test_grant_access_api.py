"""Giving an imported doctor a login, at the end of an onboarding visit.

The published page came from a public directory, so it has a placeholder
address and no password. Selling the agenda is worthless if the doctor cannot
then sign in — and the obvious workaround, registering them afresh, mints a
second profile under a different slug and leaves the printed QR aimed at the
abandoned one. That is the failure these tests exist to prevent.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import ClaimStatus, DoctorProfile, User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def _imported(db: sessionmaker[Session], slug: str) -> int:
    """A doctor as import_doctors.py leaves them: no password, fake address."""
    with db() as session:
        user = User(
            email=f"{slug}@import.invalid",
            role=UserRole.DOCTOR,
            is_active=True,
            password_hash="",
        )
        session.add(user)
        session.commit()
        session.add(
            DoctorProfile(
                user_id=user.id,
                full_name="Dr Imane Guerram",
                slug=slug,
                license_no=f"IMPORT-{user.id}",
                city="Casablanca",
                claim_status=ClaimStatus.UNCLAIMED,
            )
        )
        session.commit()
        return int(user.id)


def test_the_doctor_can_sign_in_afterwards_on_the_same_page(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    token = _admin(db)
    doctor_id = _imported(db, "dr-imane-guerram-casablanca")

    granted = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/access",
        headers=_auth(token),
        json={"email": "imane.guerram@gmail.com", "password": "cabinet-2026"},
    )
    assert granted.status_code == 200, granted.text
    # The slug must survive: it is the target of a plaque already on a wall.
    assert granted.json()["slug"] == "dr-imane-guerram-casablanca"
    assert granted.json()["claim_status"] == str(ClaimStatus.CLAIMED)

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "imane.guerram@gmail.com", "password": "cabinet-2026"},
    )
    assert login.status_code == 200, login.text

    # And it is the same account, not a second one.
    me = client.get("/api/v1/auth/me", headers=_auth(login.json()["access"]))
    assert me.status_code == 200, me.text
    assert me.json()["id"] == doctor_id


def test_the_placeholder_address_is_refused(client: TestClient, db: sessionmaker[Session]) -> None:
    token = _admin(db)
    doctor_id = _imported(db, "dr-placeholder-casablanca")

    refused = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/access",
        headers=_auth(token),
        json={"email": "dr-placeholder-casablanca@import.invalid", "password": "cabinet-2026"},
    )

    assert refused.status_code == 400, refused.text


def test_a_short_password_is_refused(client: TestClient, db: sessionmaker[Session]) -> None:
    token = _admin(db)
    doctor_id = _imported(db, "dr-short-casablanca")

    refused = client.post(
        f"/api/v1/admin/doctors/{doctor_id}/access",
        headers=_auth(token),
        json={"email": "short@gmail.com", "password": "123"},
    )

    assert refused.status_code == 400, refused.text


def test_only_an_admin_may_grant_access(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id = _imported(db, "dr-guarded-casablanca")

    assert (
        client.post(
            f"/api/v1/admin/doctors/{doctor_id}/access",
            json={"email": "x@gmail.com", "password": "cabinet-2026"},
        ).status_code
        == 401
    )
