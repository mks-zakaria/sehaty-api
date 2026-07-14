"""Doctor-search API integration tests over a live PostGIS backend.

Exercises ``GET /api/v1/doctors`` — the public "nearest VERIFIED doctors of a
specialty, ranked" endpoint. Seeding goes through the real surfaces (register ->
login -> ``PUT /doctors/me/profile`` with coords + specialties -> admin
accredit), with reputation aggregates written directly so the blended ``rank``
is observable. Takes the ``pg_*`` fixtures and SKIPs when no DB is reachable.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.specialties import SpecialtyController
from sehaty.db import ReputationScore, User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_SPECIALTY = "cardiology"

# Casablanca-ish search origin; the doctors sit at increasing distances from it.
_LAT = 33.5731
_LNG = -7.5898

# (email, slug, license, phone, lat, lng, avg_stars, review_count)
_NEAR_BEST = ("near@clinic.ma", "dr-near", "LIC-NEAR", "+212600000031", 33.5731, -7.5898, 4.9, 42)
_FAR_OK = ("far@clinic.ma", "dr-far", "LIC-FAR", "+212600000032", 33.6000, -7.5898, 3.1, 6)
_OUTSIDE = ("out@clinic.ma", "dr-out", "LIC-OUT", "+212600000033", 33.8500, -7.5898, 5.0, 99)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        admin = User(
            email="search-admin@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        return security.create_access_token(int(admin.id), UserRole.ADMIN)


def _seed_doctor(
    client: TestClient,
    db: sessionmaker[Session],
    admin_token: str,
    spec: tuple[str, str, str, str, float, float, float, int],
) -> int:
    """Register -> login -> set profile+location+specialty -> accredit -> rate."""
    email, slug, license_no, phone, lat, lng, avg_stars, review_count = spec

    reg = client.post(
        "/api/v1/auth/doctor/register",
        json={
            "email": email,
            "password": "pw-doctor-123",
            "full_name": f"Dr {slug}",
            "slug": slug,
            "license_no": license_no,
            "phone": phone,
        },
    )
    assert reg.status_code == 201, reg.text
    doctor_id = int(reg.json()["id"])

    login = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-doctor-123"},
    )
    assert login.status_code == 200, login.text
    access = login.json()["access"]

    put = client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(access),
        json={
            "full_name": f"Dr {slug}",
            "city": "Casablanca",
            "lat": lat,
            "lng": lng,
            "specialty_slugs": [_SPECIALTY],
        },
    )
    assert put.status_code == 200, put.text

    accredit = client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers=_auth(admin_token),
    )
    assert accredit.status_code == 200, accredit.text

    # Reputation aggregates are read by the search ranking; write them directly.
    with db() as session:
        session.add(
            ReputationScore(
                user_id=doctor_id,
                avg_stars=avg_stars,
                review_count=review_count,
            )
        )
        session.commit()
    return doctor_id


def test_search_ranks_verified_doctors_nearest_best_first(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    SpecialtyController.seed_defaults()
    admin_token = _seed_admin(pg_db)
    for spec in (_NEAR_BEST, _FAR_OK, _OUTSIDE):
        _seed_doctor(pg_client, pg_db, admin_token, spec)

    resp = pg_client.get(
        "/api/v1/doctors",
        params={"specialty": _SPECIALTY, "lat": _LAT, "lng": _LNG},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()

    slugs = [r["slug"] for r in rows]
    # The far-away doctor is outside the 10km default radius -> excluded.
    assert "dr-out" not in slugs
    assert slugs == ["dr-near", "dr-far"]  # ranked best/nearest first

    top = rows[0]
    assert set(top) == {
        "slug",
        "full_name",
        "photo_url",
        "city",
        "distance_m",
        "lat",
        "lng",
        "avg_stars",
        "review_count",
        "rank",
    }
    # rank is present and strictly ordered; distances are sensible metres.
    assert rows[0]["rank"] >= rows[1]["rank"]
    assert rows[0]["distance_m"] < 100  # dr-near sits on the origin
    assert 2000 < rows[1]["distance_m"] < 5000  # dr-far ~3km north
    assert rows[0]["avg_stars"] == 4.9
    assert rows[0]["review_count"] == 42


def test_search_unknown_specialty_returns_empty(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    SpecialtyController.seed_defaults()
    resp = pg_client.get(
        "/api/v1/doctors",
        params={"specialty": "no-such-specialty", "lat": _LAT, "lng": _LNG},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_search_missing_specialty_is_422(client: TestClient) -> None:
    # `specialty` is a required query param -> FastAPI rejects before the
    # controller runs, so this needs no database.
    resp = client.get("/api/v1/doctors", params={"lat": _LAT, "lng": _LNG})
    assert resp.status_code == 422, resp.text


def test_search_out_of_range_lat_is_400(client: TestClient) -> None:
    # A well-formed but out-of-range coordinate reaches the controller and
    # surfaces as a 400 via the SehatyValidationError handler.
    resp = client.get(
        "/api/v1/doctors",
        params={"specialty": _SPECIALTY, "lat": 999.0, "lng": _LNG},
    )
    assert resp.status_code == 400, resp.text
