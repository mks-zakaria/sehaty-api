"""Public doctor-directory API tests over the in-memory SQLite backend.

Exercises ``GET /api/v1/doctors/directory`` — the non-geo "browse VERIFIED
doctors by specialty + rating" endpoint. Because the controller reads a
column-only projection (never the PostGIS ``geopoint`` blob), the query compiles
on stock SQLite, so these tests use the shared ``db``/``client`` fixtures with
direct inserts (verified ``DoctorProfile`` + ``Specialty`` + ``DoctorSpecialty``
+ ``ReputationScore``) rather than the live-PostGIS ``pg_*`` fixtures.

Covers: the page shape (total + doctors with specialties/ratings), ``?specialty=``
filtering, ``?sort=name`` ordering, limit/offset pagination, and — crucially —
that ``/directory`` is served by its own route rather than being captured by the
``GET /{slug}`` catch-all (which would 404 with a doctor-not-found).
"""

from fastapi.testclient import TestClient
from sehaty.db import (
    DoctorProfile,
    DoctorSpecialty,
    ReputationScore,
    Specialty,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy.orm import Session, sessionmaker


def _seed_specialties(session: Session) -> dict[str, int]:
    """Two specialties; return {slug: id}."""
    ids: dict[str, int] = {}
    for slug, name in (("cardiology", "Cardiologie"), ("dermatology", "Dermatologie")):
        spec = Specialty(slug=slug, name_en=name, name_fr=name, name_ar=name)
        session.add(spec)
        session.flush()
        ids[slug] = int(spec.id)
    return ids


def _seed_doctor(
    session: Session,
    *,
    email: str,
    slug: str,
    full_name: str,
    license_no: str,
    specialty_ids: list[int],
    avg_stars: float,
    review_count: int,
    verified: bool = True,
    city: str = "Casablanca",
    consultation_fee: float = 300.0,
) -> int:
    """Insert a user + profile (+ specialties + reputation) directly; return id."""
    user = User(email=email, role=UserRole.DOCTOR, is_active=True, password_hash="unused")
    session.add(user)
    session.flush()
    session.add(
        DoctorProfile(
            user_id=user.id,
            full_name=full_name,
            slug=slug,
            license_no=license_no,
            city=city,
            consultation_fee=consultation_fee,
            verification_status=(
                VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
            ),
        )
    )
    for specialty_id in specialty_ids:
        session.add(DoctorSpecialty(doctor_id=user.id, specialty_id=specialty_id))
    session.add(ReputationScore(user_id=user.id, avg_stars=avg_stars, review_count=review_count))
    return int(user.id)


def _seed(db: sessionmaker[Session]) -> dict[str, int]:
    """A verified cardiologist (top-rated), a verified dermatologist, and a
    PENDING cardiologist that must never surface.
    """
    with db() as s:
        specs = _seed_specialties(s)
        _seed_doctor(
            s,
            email="alice@clinic.ma",
            slug="dr-alice",
            full_name="Alice Zahra",
            license_no="LIC-A",
            specialty_ids=[specs["cardiology"]],
            avg_stars=4.9,
            review_count=42,
        )
        _seed_doctor(
            s,
            email="bob@clinic.ma",
            slug="dr-bob",
            full_name="Bob Amine",
            license_no="LIC-B",
            specialty_ids=[specs["dermatology"]],
            avg_stars=3.2,
            review_count=5,
        )
        _seed_doctor(
            s,
            email="carol@clinic.ma",
            slug="dr-carol",
            full_name="Carol Pending",
            license_no="LIC-C",
            specialty_ids=[specs["cardiology"]],
            avg_stars=5.0,
            review_count=99,
            verified=False,
        )
        s.commit()
    return specs


def test_directory_lists_verified_doctors_no_auth(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    _seed(db)

    # No Authorization header -> public.
    resp = client.get("/api/v1/doctors/directory")
    assert resp.status_code == 200, resp.text
    page = resp.json()

    # Only the two VERIFIED doctors surface; the PENDING one is excluded.
    assert page["total"] == 2
    slugs = [d["slug"] for d in page["doctors"]]
    assert slugs == ["dr-alice", "dr-bob"]  # rating desc by default
    assert "dr-carol" not in slugs

    top = page["doctors"][0]
    assert set(top) == {
        "slug",
        "full_name",
        "photo_url",
        "city",
        "district",
        "consultation_fee",
        "avg_stars",
        "review_count",
        "specialties",
    }
    assert top["avg_stars"] == 4.9
    assert top["review_count"] == 42
    assert top["specialties"] == ["Cardiologie"]
    assert top["city"] == "Casablanca"


def test_directory_filters_by_specialty(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)

    resp = client.get("/api/v1/doctors/directory", params={"specialty": "dermatology"})
    assert resp.status_code == 200, resp.text
    page = resp.json()
    assert page["total"] == 1
    assert [d["slug"] for d in page["doctors"]] == ["dr-bob"]


def test_directory_sort_by_name(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)

    resp = client.get("/api/v1/doctors/directory", params={"sort": "name"})
    assert resp.status_code == 200, resp.text
    page = resp.json()
    # Alphabetical by full_name: "Alice Zahra" < "Bob Amine".
    assert [d["full_name"] for d in page["doctors"]] == ["Alice Zahra", "Bob Amine"]


def test_directory_pagination(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)

    first = client.get("/api/v1/doctors/directory", params={"limit": 1, "offset": 0})
    assert first.status_code == 200, first.text
    first_page = first.json()
    assert first_page["total"] == 2  # total counts all matches, not the page
    assert [d["slug"] for d in first_page["doctors"]] == ["dr-alice"]

    second = client.get("/api/v1/doctors/directory", params={"limit": 1, "offset": 1})
    assert second.status_code == 200, second.text
    second_page = second.json()
    assert second_page["total"] == 2
    assert [d["slug"] for d in second_page["doctors"]] == ["dr-bob"]


def test_directory_not_captured_by_slug_route(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    # `/directory` must resolve to the directory page, NOT the `GET /{slug}`
    # catch-all (which would 404 with a doctor-not-found for an unknown slug).
    _seed(db)
    resp = client.get("/api/v1/doctors/directory")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "doctors" in body and "total" in body  # the page, not a doctor view


def test_directory_invalid_sort_is_400(client: TestClient, db: sessionmaker[Session]) -> None:
    _seed(db)
    resp = client.get("/api/v1/doctors/directory", params={"sort": "bogus"})
    assert resp.status_code == 400, resp.text
