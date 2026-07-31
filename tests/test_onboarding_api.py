"""Onboarding over the API: find the doctor before creating a second one.

The failure this guards against is quiet and permanent. An operator searches a
name, gets nothing back, clicks "create" — and a doctor who already has a page
now has two, with their reviews on one and their printed QR pointing at the
other.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import (
    ClaimStatus,
    DoctorProfile,
    DoctorSpecialty,
    Specialty,
    User,
    UserRole,
)
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-onb@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def _seed(db: sessionmaker[Session], name: str, slug: str, city: str = "Casablanca") -> int:
    with db() as session:
        specialty = session.query(Specialty).filter_by(slug="dentistry").first()
        if specialty is None:
            specialty = Specialty(
                slug="dentistry", name_en="Dentist", name_fr="Dentiste", name_ar="طبيب أسنان"
            )
            session.add(specialty)
            session.commit()
        user = User(
            email=f"{slug}@import.invalid", role=UserRole.DOCTOR, is_active=True, password_hash=""
        )
        session.add(user)
        session.commit()
        session.add(
            DoctorProfile(
                user_id=user.id,
                full_name=name,
                slug=slug,
                license_no=f"LIC-{user.id}",
                city=city,
                claim_status=ClaimStatus.UNCLAIMED,
            )
        )
        session.add(DoctorSpecialty(doctor_id=user.id, specialty_id=specialty.id))
        session.commit()
        return int(user.id)


def test_search_finds_a_doctor_however_the_operator_types_it(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    token = _admin(db)
    _seed(db, "Dr Amina Bennani", "dr-amina-bennani-casablanca")

    for query in ("amina bennani", "Bennani", "bennani amina", "Dr. Amina Bennani"):
        found = client.get(f"/api/v1/admin/onboarding/search?q={query}", headers=_auth(token))
        assert found.status_code == 200, found.text
        assert [d["full_name"] for d in found.json()] == ["Dr Amina Bennani"], query


def test_the_city_filter_tells_two_of_the_same_name_apart(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Both Bennanis come back unfiltered; the city picks the one at this door."""
    token = _admin(db)
    _seed(db, "Dr Amina Bennani", "dr-amina-bennani-casablanca")
    _seed(db, "Dr Amina Bennani", "dr-amina-bennani-rabat", city="Rabat")

    everywhere = client.get("/api/v1/admin/onboarding/search?q=bennani", headers=_auth(token))
    assert len(everywhere.json()) == 2, everywhere.text

    in_rabat = client.get(
        "/api/v1/admin/onboarding/search?q=bennani&city=rabat", headers=_auth(token)
    )
    assert in_rabat.status_code == 200, in_rabat.text
    assert [d["city"] for d in in_rabat.json()] == ["Rabat"]


def test_the_offered_cities_all_have_a_doctor_behind_them(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """A dropdown entry that always returns nothing reads as a broken search."""
    token = _admin(db)
    _seed(db, "Dr Amina Bennani", "dr-amina-bennani-casablanca")
    _seed(db, "Dr Karim Alami", "dr-karim-alami-rabat", city="Rabat")

    offered = client.get("/api/v1/admin/onboarding/cities", headers=_auth(token))

    assert offered.status_code == 200, offered.text
    slugs = [c["slug"] for c in offered.json()]
    assert slugs == ["casablanca", "rabat"]
    for city in offered.json():
        found = client.get(
            f"/api/v1/admin/onboarding/search?q=dr&city={city['slug']}", headers=_auth(token)
        )
        assert len(found.json()) == city["doctor_count"], city


def test_creating_a_duplicate_is_refused(client: TestClient, db: sessionmaker[Session]) -> None:
    """The reason the search exists at all."""
    token = _admin(db)
    _seed(db, "Dr Amina Bennani", "dr-amina-bennani-casablanca")

    refused = client.post(
        "/api/v1/admin/onboarding/doctors",
        headers=_auth(token),
        json={
            "full_name": "Dr Amina Bennani",
            "city": "Casablanca",
            "specialty_slug": "dentistry",
        },
    )

    assert refused.status_code == 409, refused.text


def test_a_new_doctor_is_listed_never_verified(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Typing a name is not checking a licence."""
    token = _admin(db)
    _seed(db, "Dr Someone Else", "dr-someone-else-casablanca")

    created = client.post(
        "/api/v1/admin/onboarding/doctors",
        headers=_auth(token),
        json={
            "full_name": "Dr Nouvelle Praticienne",
            "city": "Casablanca",
            "specialty_slug": "dentistry",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["verification_status"] == "LISTED"
    assert created.json()["is_unclaimed"] is True


def test_onboarding_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    assert client.get("/api/v1/admin/onboarding/search?q=ab").status_code == 401
    # The city list is a read of the whole directory, including pages a patient
    # never sees, so it sits behind the same door as the search.
    assert client.get("/api/v1/admin/onboarding/cities").status_code == 401
