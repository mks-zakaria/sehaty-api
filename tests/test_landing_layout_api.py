"""Choosing a doctor's page design from the console.

The design is the part of the page the doctor actually sees, and it is what the
Pack Présence is demonstrated with at the desk. Two things must hold over the
API: the console can only offer designs the landing app really ships, and picking
one must not disturb the specialty template the sections come from.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import ClaimStatus, DoctorProfile, DoctorSpecialty, Specialty, User, UserRole
from sqlalchemy.orm import Session, sessionmaker


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-layout@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def _dentist(db: sessionmaker[Session]) -> int:
    with db() as session:
        specialty = session.query(Specialty).filter_by(slug="dentistry").first()
        if specialty is None:
            specialty = Specialty(
                slug="dentistry", name_en="Dentist", name_fr="Dentiste", name_ar="طبيب أسنان"
            )
            session.add(specialty)
            session.commit()
        user = User(
            email="layout-doc@import.invalid",
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
        session.add(DoctorSpecialty(doctor_id=user.id, specialty_id=specialty.id))
        session.commit()
        return int(user.id)


def test_the_console_is_offered_the_designs_the_pages_can_render(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Classic leads: it is what a page that nobody has touched already looks like."""
    token = _admin(db)

    offered = client.get("/api/v1/admin/doctors/layouts", headers=_auth(token))

    assert offered.status_code == 200, offered.text
    assert offered.json()[0] == "classic"
    assert set(offered.json()) == {"classic", "editorial", "compact", "clinique"}


def test_picking_a_design_leaves_the_specialty_template_inherited(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Sections come from the specialty; the design is a separate decision."""
    token = _admin(db)
    doctor_id = _dentist(db)

    saved = client.put(
        f"/api/v1/admin/doctors/{doctor_id}/landing",
        headers=_auth(token),
        json={"layout": "editorial"},
    )

    assert saved.status_code == 200, saved.text
    assert saved.json()["layout"] == "editorial"
    assert saved.json()["layout_is_default"] is False
    assert saved.json()["template"] == "dentistry"
    assert saved.json()["template_is_default"] is True


def test_a_design_the_landing_app_cannot_render_is_refused(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Better a 400 at the desk than a console that claims a design the page
    does not have."""
    token = _admin(db)
    doctor_id = _dentist(db)

    refused = client.put(
        f"/api/v1/admin/doctors/{doctor_id}/landing",
        headers=_auth(token),
        json={"layout": "brutalist"},
    )

    assert refused.status_code == 400, refused.text
    unchanged = client.get(f"/api/v1/admin/doctors/{doctor_id}/landing", headers=_auth(token))
    assert unchanged.json()["layout"] == "classic"


def test_an_unpaid_page_still_keeps_its_design(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """A page whose QR is on a plaque must not restyle itself when a payment lapses."""
    token = _admin(db)
    doctor_id = _dentist(db)
    client.put(
        f"/api/v1/admin/doctors/{doctor_id}/landing",
        headers=_auth(token),
        json={"layout": "compact", "accent": "#123456"},
    )

    free = client.get(f"/api/v1/admin/doctors/{doctor_id}/landing", headers=_auth(token))

    assert free.json()["is_personalized"] is False
    assert free.json()["layout"] == "compact"
    # The paid styling is withheld; the design is not paid styling.
    assert free.json()["accent"] is None


def test_the_design_picker_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    assert client.get("/api/v1/admin/doctors/layouts").status_code == 401
