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


def test_the_platform_writes_and_a_doctor_signs(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """The whole content trade, over the API.

    We supply the writing and the citation; a doctor supplies the standing; the
    published page carries their name and links back to their own page. Each half
    is worthless alone.
    """
    admin = _admin(db)
    doctor = _doctor(
        db, email="signer@c.ma", slug="dr-signer-casa", claim=ClaimStatus.CLAIMED
    )

    drafted = client.post(
        "/api/v1/admin/articles",
        headers=_auth(admin),
        json={
            "title": "C'est quoi une hernie discale ?",
            "body": BODY,
            "locale": "fr",
            "specialty_slug": "orthopedics",
            "sources": [{"work": "Gray's Anatomy", "locator": "41e éd., ch. 12"}],
        },
    )
    assert drafted.status_code == 201, drafted.text
    assert drafted.json()["author_id"] is None
    article_id = drafted.json()["id"]

    signed = client.post(
        f"/api/v1/doctors/me/articles/{article_id}/validate",
        headers=_auth(doctor),
        json={"verdict": "ENRICHED", "note": "Ajout du délai de prise en charge CNSS."},
    )
    assert signed.status_code == 200, signed.text
    assert [v["slug"] for v in signed.json()["validations"]] == ["dr-signer-casa"]
    assert signed.json()["validations"][0]["verdict"] == "ENRICHED"

    client.post(
        f"/api/v1/admin/articles/{article_id}/review",
        headers=_auth(admin),
        json={"approve": True},
    )
    public = client.get(f"/api/v1/articles/{drafted.json()['slug']}")

    assert public.status_code == 200, public.text
    # The byline the landing page renders, and the link that makes signing worth
    # a doctor's five minutes.
    assert public.json()["validations"][0]["slug"] == "dr-signer-casa"
    assert public.json()["sources"][0]["work"] == "Gray's Anatomy"


def test_only_an_admin_may_publish_under_the_platforms_name(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """An authorless article is the one thing a doctor must not be able to make."""
    doctor = _doctor(
        db, email="notadmin@c.ma", slug="dr-notadmin", claim=ClaimStatus.CLAIMED
    )
    payload = {
        "title": "C'est quoi une hernie discale ?",
        "body": BODY,
        "locale": "fr",
        "sources": [{"work": "Gray's Anatomy"}],
    }

    assert client.post("/api/v1/admin/articles", json=payload).status_code == 401
    assert (
        client.post("/api/v1/admin/articles", headers=_auth(doctor), json=payload).status_code
        == 403
    )


def test_an_unclaimed_doctor_cannot_sign(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Same funnel as writing: signing requires owning your page."""
    admin = _admin(db)
    cold = _doctor(db, email="cold-sign@c.ma", slug="dr-cold-sign", claim=ClaimStatus.UNCLAIMED)
    drafted = client.post(
        "/api/v1/admin/articles",
        headers=_auth(admin),
        json={
            "title": "C'est quoi une hernie discale ?",
            "body": BODY,
            "locale": "fr",
            "sources": [{"work": "Gray's Anatomy"}],
        },
    )

    refused = client.post(
        f"/api/v1/doctors/me/articles/{drafted.json()['id']}/validate",
        headers=_auth(cold),
        json={"verdict": "VALIDATED"},
    )

    assert refused.status_code == 403, refused.text


def _publish_platform_article(client: TestClient, admin: str) -> dict:
    drafted = client.post(
        "/api/v1/admin/articles",
        headers=_auth(admin),
        json={
            "title": "C'est quoi une hernie discale ?",
            "body": BODY,
            "locale": "fr",
            "sources": [{"work": "Pathology Illustrated", "locator": "p. 1"}],
        },
    )
    article = drafted.json()
    client.post(
        f"/api/v1/admin/articles/{article['id']}/review",
        headers=_auth(admin),
        json={"approve": True},
    )
    return article


def test_a_reader_votes_without_an_account(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Requiring a login to say "this did not help" would collect the opinion of
    the people who already trust us and miss everyone we have to convince."""
    article = _publish_platform_article(client, _admin(db))

    voted = client.post(f"/api/v1/articles/{article['slug']}/vote", json={"helpful": True})

    assert voted.status_code == 200, voted.text
    assert (voted.json()["helpful_votes"], voted.json()["total_votes"]) == (1, 1)


def test_one_reader_cannot_vote_twice(client: TestClient, db: sessionmaker[Session]) -> None:
    article = _publish_platform_article(client, _admin(db))
    url = f"/api/v1/articles/{article['slug']}/vote"

    client.post(url, json={"helpful": True})
    client.post(url, json={"helpful": True})
    changed = client.post(url, json={"helpful": False})

    # Still one person — who has changed their mind.
    assert (changed.json()["helpful_votes"], changed.json()["total_votes"]) == (0, 1)


def test_readers_behind_different_addresses_are_counted_separately(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Behind the droplet's nginx every reader shares a peer address, so the
    forwarded header has to be what distinguishes them — otherwise the first
    vote of the day locks out the whole country."""
    article = _publish_platform_article(client, _admin(db))
    url = f"/api/v1/articles/{article['slug']}/vote"

    client.post(url, json={"helpful": True}, headers={"x-forwarded-for": "41.0.0.1"})
    second = client.post(
        url, json={"helpful": True}, headers={"x-forwarded-for": "41.0.0.2"}
    )

    assert second.json()["total_votes"] == 2


def test_a_draft_takes_no_votes(client: TestClient, db: sessionmaker[Session]) -> None:
    admin = _admin(db)
    drafted = client.post(
        "/api/v1/admin/articles",
        headers=_auth(admin),
        json={
            "title": "Brouillon non publié",
            "body": BODY,
            "locale": "fr",
            "sources": [{"work": "Pathology Illustrated", "locator": "p. 1"}],
        },
    )

    refused = client.post(
        f"/api/v1/articles/{drafted.json()['slug']}/vote", json={"helpful": True}
    )

    assert refused.status_code == 404, refused.text


def test_the_beacon_records_the_channel_a_reader_came_from(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Topic choice should run on this, not on published disease prevalence."""
    admin = _admin(db)
    article = _publish_platform_article(client, admin)

    for source in ("google", "whatsapp", "whatsapp"):
        beacon = client.post(
            f"/api/v1/articles/{article['slug']}/events",
            json={"type": "PAGE_VIEW", "source": source},
        )
        assert beacon.status_code == 204, beacon.text

    report = client.get("/api/v1/admin/articles/traffic", headers=_auth(admin))
    row = report.json()[0]
    assert row["views"] == 3
    assert (row["from_google"], row["from_whatsapp"]) == (1, 2)


def test_a_beacon_never_fails_the_page_it_was_sent_from(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    """Fire-and-forget from a page a patient is reading: an unknown slug or a
    junk event type must not surface as an error."""
    assert (
        client.post("/api/v1/articles/no-such-thing/events", json={"type": "PAGE_VIEW"}).status_code
        == 204
    )


def test_the_traffic_report_is_admin_only(client: TestClient, db: sessionmaker[Session]) -> None:
    assert client.get("/api/v1/admin/articles/traffic").status_code == 401
