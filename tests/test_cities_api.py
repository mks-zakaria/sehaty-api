"""Cities API tests over the in-memory SQLite backend.

Exercises ``GET /api/v1/cities``, ``/{city}/districts`` and
``/{city}/specialties`` — the browse axes the landing site calls at build time
to decide which ``/{city}`` and ``/{city}/{specialty}`` pages to generate — plus
the ``?city=``/``?district=`` filters on ``/doctors/directory``.

Like the directory suite, the controllers read column-only projections (never
the PostGIS ``geopoint`` blob), so these run on the shared SQLite fixtures with
direct inserts rather than the live-PostGIS ``pg_*`` ones.
"""

from fastapi.testclient import TestClient
from sehaty.db import (
    DoctorProfile,
    DoctorSpecialty,
    Specialty,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy.orm import Session, sessionmaker


def _seed(db: sessionmaker[Session]) -> None:
    """Three Casablanca doctors (city spelled three ways), one in Rabat, and
    two that must never surface: a PENDING doctor and a deactivated one.
    """
    with db() as s:
        specs: dict[str, int] = {}
        for slug, fr in (("dentistry", "Dentiste"), ("cardiology", "Cardiologue")):
            spec = Specialty(slug=slug, name_en=fr, name_fr=fr, name_ar=fr, name_ary=fr)
            s.add(spec)
            s.flush()
            specs[slug] = int(spec.id)

        rows = [
            ("a@c.ma", "dr-a", "Dr A", "Casablanca", "Maârif", "dentistry", True, True),
            ("b@c.ma", "dr-b", "Dr B", "casablanca", "Maarif", "dentistry", True, True),
            ("c@c.ma", "dr-c", "Dr C", "CASABLANCA", "Gauthier", "cardiology", True, True),
            ("d@c.ma", "dr-d", "Dr D", "Rabat", "Agdal", "dentistry", True, True),
            ("e@c.ma", "dr-e", "Dr E", "Fès", "Atlas", "dentistry", False, True),
            ("f@c.ma", "dr-f", "Dr F", "Tanger", "Malabata", "dentistry", True, False),
        ]
        for email, slug, name, city, district, specialty, verified, active in rows:
            user = User(email=email, role=UserRole.DOCTOR, is_active=active, password_hash="x")
            s.add(user)
            s.flush()
            s.add(
                DoctorProfile(
                    user_id=user.id,
                    full_name=name,
                    slug=slug,
                    license_no=f"LIC-{slug}",
                    city=city,
                    district=district,
                    verification_status=(
                        VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
                    ),
                )
            )
            s.add(DoctorSpecialty(doctor_id=user.id, specialty_id=specs[specialty]))
        s.commit()


def test_lists_cities_grouping_spellings(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    resp = client.get("/api/v1/cities")
    assert resp.status_code == 200, resp.text
    cities = {c["slug"]: c for c in resp.json()}

    # Three spellings of Casablanca are one browse page with one count.
    assert set(cities) == {"casablanca", "rabat"}
    assert cities["casablanca"]["doctor_count"] == 3
    assert cities["rabat"]["doctor_count"] == 1
    assert set(cities["casablanca"]) == {"slug", "label", "doctor_count"}


def test_cities_exclude_unverified_and_inactive(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)
    slugs = {c["slug"] for c in client.get("/api/v1/cities").json()}
    # A city whose only doctor is PENDING or deactivated must never become a
    # page — the sales pitch would point at an empty listing.
    assert "fes" not in slugs
    assert "tanger" not in slugs


def test_cities_ordered_by_doctor_count(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    assert [c["slug"] for c in client.get("/api/v1/cities").json()] == [
        "casablanca",
        "rabat",
    ]


def test_lists_districts_of_a_city(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    resp = client.get("/api/v1/cities/casablanca/districts")
    assert resp.status_code == 200, resp.text
    districts = {d["slug"]: d["doctor_count"] for d in resp.json()}
    # "Maârif" and "Maarif" collapse to one neighbourhood.
    assert districts == {"maarif": 2, "gauthier": 1}


def test_unknown_city_districts_is_empty_not_404(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)
    resp = client.get("/api/v1/cities/atlantis/districts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_lists_city_specialties_with_local_counts(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)
    resp = client.get("/api/v1/cities/casablanca/specialties")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    counts = {r["slug"]: r["doctor_count"] for r in rows}
    # Rabat's dentist must not inflate Casablanca's count.
    assert counts == {"dentistry": 2, "cardiology": 1}
    # Localized names ship so the city hub can render in FR/AR/Darija.
    assert set(rows[0]) == {
        "slug",
        "name_en",
        "name_fr",
        "name_ar",
        "name_ary",
        "doctor_count",
    }


def test_city_specialties_ordered_by_count(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    rows = client.get("/api/v1/cities/casablanca/specialties").json()
    assert [r["slug"] for r in rows] == ["dentistry", "cardiology"]


def test_directory_filters_by_city_slug(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    page = client.get("/api/v1/doctors/directory", params={"city": "casablanca"}).json()
    assert page["total"] == 3
    assert {d["slug"] for d in page["doctors"]} == {"dr-a", "dr-b", "dr-c"}


def test_directory_filters_by_district_slug(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    page = client.get(
        "/api/v1/doctors/directory", params={"city": "casablanca", "district": "maarif"}
    ).json()
    assert page["total"] == 2
    assert {d["slug"] for d in page["doctors"]} == {"dr-a", "dr-b"}


def test_directory_combines_city_and_specialty(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)
    page = client.get(
        "/api/v1/doctors/directory", params={"city": "casablanca", "specialty": "cardiology"}
    ).json()
    assert page["total"] == 1
    assert page["doctors"][0]["slug"] == "dr-c"


def test_directory_unknown_city_is_empty_page(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)
    resp = client.get("/api/v1/doctors/directory", params={"city": "atlantis"})
    # An unknown city is a 404 concern for the landing route, not a 400 here.
    assert resp.status_code == 200
    assert resp.json() == {"total": 0, "doctors": []}
