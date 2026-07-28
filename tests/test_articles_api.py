"""Articles over the API: who may write, who may publish, who may read.

Three audiences on one resource. The guard that matters most is that the public
route never serves anything a human has not approved — a draft leaking as a
preview would put unreviewed medical advice under the platform's name.
"""

from fastapi.testclient import TestClient
from sehaty.core import security
from sehaty.db import ClaimStatus, DoctorProfile, User, UserRole
from sqlalchemy.orm import Session, sessionmaker

BODY = (
    "Oui, dans la majorité des cas, à condition d'adapter le traitement et de "
    "surveiller la glycémie plus souvent. Un diabétique de type 2 équilibré peut "
    "généralement jeûner après avoir revu les doses avec son médecin."
)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _doctor(db: sessionmaker[Session], *, email: str, slug: str, claim: ClaimStatus) -> str:
    with db() as session:
        user = User(email=email, role=UserRole.DOCTOR, is_active=True, password_hash="x")
        session.add(user)
        session.commit()
        session.add(
            DoctorProfile(
                user_id=user.id,
                full_name="Dr Amina Bennani",
                slug=slug,
                license_no=f"LIC-{user.id}",
                city="Casablanca",
                claim_status=claim,
            )
        )
        session.commit()
        return security.create_access_token(int(user.id), UserRole.DOCTOR)


def _admin(db: sessionmaker[Session]) -> str:
    with db() as session:
        user = User(
            email="staff-art@sehaty.test", role=UserRole.ADMIN, is_active=True, password_hash="x"
        )
        session.add(user)
        session.commit()
        return security.create_access_token(int(user.id), UserRole.ADMIN)


def test_the_public_never_sees_an_unreviewed_answer(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor = _doctor(db, email="w@c.ma", slug="dr-w", claim=ClaimStatus.CLAIMED)
    created = client.post(
        "/api/v1/doctors/me/articles",
        headers=_auth(doctor),
        json={"title": "Est-ce qu'un diabétique peut jeûner ?", "body": BODY, "locale": "fr"},
    )
    assert created.status_code == 201, created.text
    slug = created.json()["slug"]

    assert client.get("/api/v1/articles").json() == []
    assert client.get(f"/api/v1/articles/{slug}").status_code == 404

    client.post(f"/api/v1/doctors/me/articles/{created.json()['id']}/submit", headers=_auth(doctor))
    # Submitted is still not published.
    assert client.get("/api/v1/articles").json() == []

    admin = _admin(db)
    approved = client.post(
        f"/api/v1/admin/articles/{created.json()['id']}/review",
        headers=_auth(admin),
        json={"approve": True},
    )
    assert approved.status_code == 200, approved.text

    public = client.get(f"/api/v1/articles/{slug}")
    assert public.status_code == 200
    assert public.json()["author_slug"] == "dr-w"
    assert len(client.get("/api/v1/articles").json()) == 1


def test_an_unclaimed_doctor_is_pushed_to_claim_first(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor = _doctor(db, email="cold@c.ma", slug="dr-cold", claim=ClaimStatus.UNCLAIMED)

    refused = client.post(
        "/api/v1/doctors/me/articles",
        headers=_auth(doctor),
        json={"title": "Une question", "body": BODY},
    )

    assert refused.status_code == 403, refused.text


def test_a_doctor_cannot_publish_their_own_answer(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor = _doctor(db, email="self@c.ma", slug="dr-self", claim=ClaimStatus.CLAIMED)
    article_id = client.post(
        "/api/v1/doctors/me/articles",
        headers=_auth(doctor),
        json={"title": "Ma question", "body": BODY},
    ).json()["id"]

    assert (
        client.post(
            f"/api/v1/admin/articles/{article_id}/review",
            headers=_auth(doctor),
            json={"approve": True},
        ).status_code
        == 403
    )


def test_a_rejection_reaches_the_author_with_its_reason(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    doctor = _doctor(db, email="r@c.ma", slug="dr-r", claim=ClaimStatus.CLAIMED)
    article_id = client.post(
        "/api/v1/doctors/me/articles",
        headers=_auth(doctor),
        json={"title": "Ma clinique est la meilleure", "body": BODY},
    ).json()["id"]
    client.post(f"/api/v1/doctors/me/articles/{article_id}/submit", headers=_auth(doctor))

    client.post(
        f"/api/v1/admin/articles/{article_id}/review",
        headers=_auth(_admin(db)),
        json={"approve": False, "note": "Ton promotionnel — l'Ordre l'interdit."},
    )

    mine = client.get("/api/v1/doctors/me/articles", headers=_auth(doctor)).json()
    assert mine[0]["status"] == "REJECTED"
    assert "Ordre" in mine[0]["review_note"]


def test_the_review_queue_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    doctor = _doctor(db, email="q@c.ma", slug="dr-q", claim=ClaimStatus.CLAIMED)

    assert client.get("/api/v1/admin/articles/pending").status_code == 401
    assert client.get("/api/v1/admin/articles/pending", headers=_auth(doctor)).status_code == 403
