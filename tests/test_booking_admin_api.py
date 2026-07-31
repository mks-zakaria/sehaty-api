"""Opening and closing one doctor's agenda from the console.

The switch thrown at the cabinet while the pack is being sold. Two things have to
hold over the API, and they pull in opposite directions: switching on has to
actually deliver the agenda the operator just promised, and it must never hand
the paid engine to a doctor whose subscription has lapsed.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import (
    ClaimStatus,
    DoctorProfile,
    Plan,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-rdv@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def _doctor(db: sessionmaker[Session]) -> int:
    """An imported doctor as the visit finds them: no subscription, no login."""
    with db() as session:
        if session.query(Plan).filter_by(code="basic").first() is None:
            session.add(Plan(code="basic", name="Basic", price_month=199.0))
        user = User(
            email="rdv-doc@import.invalid",
            role=UserRole.DOCTOR,
            is_active=True,
            password_hash="",
        )
        session.add(user)
        session.commit()
        session.add(
            DoctorProfile(
                user_id=user.id,
                full_name="Dr Amina Bennani",
                slug="dr-amina-bennani-casablanca",
                license_no=f"LIC-{user.id}",
                city="Casablanca",
                claim_status=ClaimStatus.UNCLAIMED,
            )
        )
        session.commit()
        return int(user.id)


def test_an_imported_doctor_starts_with_no_agenda(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Not an error state — it is every doctor in the directory."""
    token = _admin(db)
    doctor_id = _doctor(db)

    state = client.get(f"/api/v1/admin/doctors/{doctor_id}/booking", headers=_auth(token))

    assert state.status_code == 200, state.text
    assert state.json()["booking_enabled"] is False
    assert state.json()["reason"] == "no_subscription"
    assert state.json()["manually_disabled"] is False


def test_switching_on_at_the_visit_opens_the_agenda(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """One tap has to deliver what the operator just promised across the desk."""
    token = _admin(db)
    doctor_id = _doctor(db)

    opened = client.put(
        f"/api/v1/admin/doctors/{doctor_id}/booking",
        headers=_auth(token),
        json={"enabled": True},
    )

    assert opened.status_code == 200, opened.text
    assert opened.json()["booking_enabled"] is True
    # The pack's three free months, started here rather than at first payment.
    assert opened.json()["status"].endswith("TRIALING")


def test_switching_off_survives_the_subscription(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """A cabinet that takes walk-ins is still a paying customer."""
    token = _admin(db)
    doctor_id = _doctor(db)
    client.put(
        f"/api/v1/admin/doctors/{doctor_id}/booking",
        headers=_auth(token),
        json={"enabled": True},
    )

    closed = client.put(
        f"/api/v1/admin/doctors/{doctor_id}/booking",
        headers=_auth(token),
        json={"enabled": False},
    )

    assert closed.json()["booking_enabled"] is False
    assert closed.json()["reason"] == "switched_off"
    assert closed.json()["manually_disabled"] is True
    # Still subscribed: the console must not report them as a collections case.
    assert closed.json()["status"].endswith("TRIALING")


def test_the_public_page_stops_offering_booking(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    """The switch has to reach the page, which is the only place it matters.

    `booking_enabled` on the public payload is what hides the Prendre
    rendez-vous button, so this is the assertion that says the feature works at
    all rather than only in the console.

    On PostGIS rather than the in-memory SQLite the rest of this file uses: the
    public doctor payload projects the pin through ``ST_X``/``ST_Y``, which
    SQLite cannot run. Skips cleanly when no database is reachable.
    """
    client, db = pg_client, pg_db
    token = _admin(db)
    doctor_id = _doctor(db)
    with db() as session:
        profile = session.get(DoctorProfile, doctor_id)
        profile.verification_status = VerificationStatus.VERIFIED
        slug = profile.slug
        session.commit()

    client.put(
        f"/api/v1/admin/doctors/{doctor_id}/booking",
        headers=_auth(token),
        json={"enabled": True},
    )
    opened = client.get(f"/api/v1/doctors/{slug}")
    assert opened.status_code == 200, opened.text
    assert opened.json()["booking_enabled"] is True

    client.put(
        f"/api/v1/admin/doctors/{doctor_id}/booking",
        headers=_auth(token),
        json={"enabled": False},
    )
    closed = client.get(f"/api/v1/doctors/{slug}")

    assert closed.json()["booking_enabled"] is False
    # And the page itself is untouched: closing an agenda is not delisting a
    # doctor, and the QR code on their wall still has to resolve.
    assert closed.status_code == 200
    assert closed.json()["slug"] == slug


def test_the_switch_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor_id = _doctor(db)

    assert client.get(f"/api/v1/admin/doctors/{doctor_id}/booking").status_code == 401
    assert (
        client.put(
            f"/api/v1/admin/doctors/{doctor_id}/booking", json={"enabled": True}
        ).status_code
        == 401
    )
