"""Doctor-profile API integration tests over a live PostGIS backend.

Unlike the SQLite-backed auth/admin suites, these exercise the real PostGIS
``geopoint`` round-trip (WKTElement write -> ST_X/ST_Y read), so they take the
``pg_client``/``pg_db`` fixtures and SKIP when no database is reachable.

Flow under test: a DOCTOR registers -> logs in -> ``PUT /doctors/me/profile``
with coordinates + specialties (200 ``{slug}``); the public page is 404 while
PENDING; after an admin accredits, ``GET /doctors/{slug}`` returns 200 with the
same lat/lng (±1e-6) and specialties. ``GET /specialties`` returns the seeded
catalogue, and a non-doctor ``PUT`` is 403.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.core.controllers.specialties import SpecialtyController
from sehaty.db import User, UserRole
from sqlalchemy.orm import Session, sessionmaker

_DOCTOR = {
    "email": "geo-doc@clinic.ma",
    "password": "pw-doctor-123",
    "full_name": "Dr Geo Test",
    "slug": "dr-geo-seed",
    "license_no": "LIC-GEO-1",
    "phone": "+212600000021",
}

# Casablanca-ish coordinates for the round-trip assertion.
_LAT = 33.589886
_LNG = -7.603869
_SPECIALTIES = ["cardiology", "dermatology"]
# A typical Casablanca week: 0=Monday, split at midday. Already sorted, so the
# controller's normalization returns it unchanged and the round-trip is exact.
_OPENING_HOURS = [
    {"weekday": 0, "ranges": [["09:00", "12:30"], ["15:00", "19:00"]]},
    {"weekday": 1, "ranges": [["09:00", "12:30"]]},
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_doctor(client: TestClient) -> int:
    reg = client.post("/api/v1/auth/doctor/register", json=_DOCTOR)
    assert reg.status_code == 201, reg.text
    return int(reg.json()["id"])


def _login(client: TestClient) -> str:
    login = client.post(
        "/api/v1/auth/login",
        json={"email": _DOCTOR["email"], "password": _DOCTOR["password"]},
    )
    assert login.status_code == 200, login.text
    return login.json()["access"]


def _seed_admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        admin = User(
            email="geo-admin@sehaty.ma",
            role=UserRole.ADMIN,
            is_active=True,
            password_hash="unused",
        )
        session.add(admin)
        session.commit()
        admin_id = int(admin.id)
    return security.create_access_token(admin_id, UserRole.ADMIN)


def test_doctor_profile_upsert_and_public_page(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    seeded = SpecialtyController.seed_defaults()
    assert seeded > 0

    doctor_id = _register_doctor(pg_client)
    access = _login(pg_client)

    # DOCTOR upserts their profile with coordinates + specialties -> {slug}.
    put = pg_client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(access),
        json={
            "full_name": "Dr Geo Test",
            "bio": "Heart specialist",
            "city": "Casablanca",
            "address": "12 Boulevard Zerktouni",
            "consultation_fee": 400.0,
            "lat": _LAT,
            "lng": _LNG,
            "languages": ["ar", "fr"],
            "phone_fixe": "+212522445566",
            "whatsapp": "+212661445566",
            "opening_hours": _OPENING_HOURS,
            # Mixed case + a duplicate: the controller lowercases and dedupes.
            "insurances": ["CNSS", "cnops", "CNSS"],
            "tiers_payant": True,
            "specialty_slugs": _SPECIALTIES,
        },
    )
    assert put.status_code == 200, put.text
    slug = put.json()["slug"]
    assert slug

    # PENDING -> the public page must not resolve (no leaking unverified docs).
    assert pg_client.get(f"/api/v1/doctors/{slug}").status_code == 404

    # Admin accredits -> the doctor becomes VERIFIED.
    admin_token = _seed_admin(pg_db)
    accredit = pg_client.post(
        f"/api/v1/admin/professionals/{doctor_id}/accredit",
        headers=_auth(admin_token),
    )
    assert accredit.status_code == 200, accredit.text

    # Now the public page resolves with the round-tripped coordinates + specs.
    page = pg_client.get(f"/api/v1/doctors/{slug}")
    assert page.status_code == 200, page.text
    body = page.json()
    # `id` mirrors core's `DoctorView.id` (the doctor's user id) — the handle
    # the `/dr` → `/book` front flow POSTs an appointment with.
    assert body["id"] == doctor_id
    assert body["slug"] == slug
    assert body["full_name"] == "Dr Geo Test"
    assert body["city"] == "Casablanca"
    assert body["consultation_fee"] == 400.0
    assert abs(body["lat"] - _LAT) < 1e-6
    assert abs(body["lng"] - _LNG) < 1e-6
    assert body["verification_status"].endswith("VERIFIED")
    returned_slugs = {s["slug"] for s in body["specialties"]}
    assert returned_slugs == set(_SPECIALTIES)
    # Public-landing fields: the page's CTAs, hours and insurance block.
    assert body["phone_fixe"] == "+212522445566"
    assert body["whatsapp"] == "+212661445566"
    # A doctor who gave no mobile must serialize as null, not be omitted.
    assert body["phone_mobile"] is None
    assert body["opening_hours"] == _OPENING_HOURS
    assert body["insurances"] == ["cnss", "cnops"]
    assert body["tiers_payant"] is True
    # The landing app switches on both of these: the template decides which
    # sections the page has, the layout decides which of the four designs builds
    # it. A page served without them renders as the plain default, so they are
    # part of the public contract and not merely an admin field.
    assert body["landing"]["layout"] == "classic"
    assert body["landing"]["layout_is_default"] is True
    assert body["landing"]["template"]


def test_specialties_endpoint_lists_seeded_catalogue(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    seeded = SpecialtyController.seed_defaults()
    resp = pg_client.get("/api/v1/specialties")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == seeded
    row = rows[0]
    assert set(row) == {"id", "slug", "name_en", "name_fr", "name_ar", "name_ary"}
    assert "cardiology" in {r["slug"] for r in rows}


def test_non_doctor_cannot_upsert_profile(
    pg_client: TestClient, pg_db: sessionmaker[Session]
) -> None:
    # An ADMIN (non-DOCTOR) token is rejected by the DOCTOR role guard -> 403.
    admin_token = _seed_admin(pg_db)
    resp = pg_client.put(
        "/api/v1/doctors/me/profile",
        headers=_auth(admin_token),
        json={"full_name": "Not A Doctor"},
    )
    assert resp.status_code == 403, resp.text
