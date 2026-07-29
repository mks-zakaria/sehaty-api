"""Backup and restore over the API.

This endpoint hands out the whole doctor table — names, addresses, phone
numbers — so the access check is the first thing worth pinning, and the dry-run
default is the second.

The export/restore round trip lives in the core suite instead: reading a
geopoint back needs `ST_X`/`ST_Y` over a PostGIS cast, which this SQLite fixture
cannot compile.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import DoctorProfile, User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-bk@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def _doctor(db: sessionmaker[Session], slug: str, **kw) -> None:
    with db() as session:
        user = User(
            email=f"{slug}@import.invalid", role=UserRole.DOCTOR, is_active=True, password_hash=""
        )
        session.add(user)
        session.commit()
        session.add(
            DoctorProfile(
                user_id=user.id,
                full_name="Dr Backup",
                slug=slug,
                license_no=f"LIC-{user.id}",
                city="Casablanca",
                **kw,
            )
        )
        session.commit()


def test_restore_defaults_to_a_dry_run(client: TestClient, db: sessionmaker[Session]) -> None:
    """An operator should see what would change before anything does."""
    token = _admin(db)
    _doctor(db, "dr-dryrun")

    report = client.post(
        "/api/v1/admin/backup/restore",
        headers=_auth(token),
        json={
            "schema_version": 1,
            "rows": [{"slug": "dr-dryrun", "address": "45 rue Ibn Batouta"}],
        },
    )

    assert report.status_code == 200, report.text
    # It reports what it *would* do …
    assert report.json()["updated"] == 1
    with db() as session:
        stored = session.query(DoctorProfile).filter_by(slug="dr-dryrun").one()
        # … and did not do it.
        assert stored.address is None


def test_the_whole_table_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    """It contains every doctor's name, address and phone number."""
    assert client.get("/api/v1/admin/backup").status_code == 401
    assert (
        client.post("/api/v1/admin/backup/restore", json={"schema_version": 1}).status_code == 401
    )
