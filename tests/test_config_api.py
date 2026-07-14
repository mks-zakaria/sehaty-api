"""Admin configuration API integration tests over a TestClient with SQLite.

The config surface (ranking weights + feature flags) is thin CRUD over two small
tables. The shared ``db``/``client`` fixtures build every table, including
``ranking_weights`` and ``feature_flags``, on the in-memory SQLite engine; admins
are seeded directly via the session factory. Covers: reading the ranking-weights
defaults; a partial weight update (one field changes, the rest are untouched);
creating/reading a feature flag; and role gating (a non-admin on any config
route -> 403).
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: sessionmaker[Session], email: str = "cfg-admin@sehaty.ma") -> str:
    with db() as session:
        admin = User(email=email, role=UserRole.ADMIN, is_active=True, password_hash="unused")
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def _seed_patient_token(db: sessionmaker[Session]) -> str:
    with db() as session:
        patient = User(
            email="cfg-patient@sehaty.ma",
            role=UserRole.PATIENT,
            is_active=True,
            password_hash="unused",
        )
        session.add(patient)
        session.commit()
        patient_id = int(patient.id)
    return security.create_access_token(patient_id, UserRole.PATIENT)


def test_admin_get_ranking_weights_defaults(client: TestClient, db: sessionmaker[Session]) -> None:
    admin_token = _seed_admin(db)

    resp = client.get("/api/v1/admin/config/ranking-weights", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {
        "w_rating": 1.0,
        "w_distance": 1.0,
        "w_responsiveness": 0.5,
        "w_verified": 0.5,
        "w_recency": 0.25,
    }


def test_admin_partial_update_ranking_weights(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    admin_token = _seed_admin(db)

    resp = client.put(
        "/api/v1/admin/config/ranking-weights",
        json={"w_rating": 2.0},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["w_rating"] == 2.0

    # GET reflects the change; the other weights are untouched at their defaults.
    resp = client.get("/api/v1/admin/config/ranking-weights", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["w_rating"] == 2.0
    assert body["w_distance"] == 1.0
    assert body["w_responsiveness"] == 0.5
    assert body["w_verified"] == 0.5
    assert body["w_recency"] == 0.25


def test_admin_set_and_list_feature_flag(client: TestClient, db: sessionmaker[Session]) -> None:
    admin_token = _seed_admin(db)

    resp = client.put(
        "/api/v1/admin/config/feature-flags/telehealth",
        json={"enabled": True},
        headers=_auth(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"key": "telehealth", "enabled": True, "description": None}

    resp = client.get("/api/v1/admin/config/feature-flags", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["flags"]["telehealth"] is True


def test_non_admin_hitting_config_is_403(client: TestClient, db: sessionmaker[Session]) -> None:
    patient_token = _seed_patient_token(db)

    assert (
        client.get("/api/v1/admin/config/ranking-weights", headers=_auth(patient_token)).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/admin/config/ranking-weights",
            json={"w_rating": 2.0},
            headers=_auth(patient_token),
        ).status_code
        == 403
    )
    assert (
        client.get("/api/v1/admin/config/feature-flags", headers=_auth(patient_token)).status_code
        == 403
    )
    assert (
        client.put(
            "/api/v1/admin/config/feature-flags/telehealth",
            json={"enabled": True},
            headers=_auth(patient_token),
        ).status_code
        == 403
    )
