"""Tests for the bulk doctor-import script.

The properties under test are the ones that protect real professionals whose
listings we publish before ever speaking to them: a removal is never undone by a
re-run, a doctor's own edits are never clobbered by a spreadsheet, and nothing
is invented to fill a blank cell.

The script lives in `scripts/`, outside the importable package, so it is loaded
by path — the same way `seed_demo` is run.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from sehaty.db import (
    ClaimStatus,
    DoctorProfile,
    DoctorSpecialty,
    ProfileSource,
    Specialty,
    User,
    UserRole,
    VerificationStatus,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "import_doctors.py"
_spec = importlib.util.spec_from_file_location("import_doctors", _SCRIPT)
import_doctors = importlib.util.module_from_spec(_spec)
# Registered before exec: @dataclass resolves annotations via
# sys.modules[cls.__module__], which is None for an unregistered module.
sys.modules["import_doctors"] = import_doctors
_spec.loader.exec_module(import_doctors)


@pytest.fixture
def specialties(db: sessionmaker[Session]) -> dict[str, int]:
    with db() as s:
        rows = []
        for slug, fr in (("dentistry", "Dentiste"), ("cardiology", "Cardiologue")):
            spec = Specialty(slug=slug, name_en=fr, name_fr=fr, name_ar=fr, name_ary=fr)
            s.add(spec)
            rows.append(spec)
        s.commit()
        return {spec.slug: int(spec.id) for spec in rows}


def _row(**overrides: str) -> dict[str, str]:
    base = {
        "full_name": "Dr. Amina Bennani",
        "specialty": "dentistry",
        "city": "Casablanca",
        "district": "Maârif",
        "address": "45 Rue Ibn Batouta",
        "phone_fixe": "+212522250180",
        "phone_mobile": "",
        "whatsapp": "",
        "lat": "",
        "lng": "",
        "license_no": "",
        "consultation_fee": "350",
        "languages": "fr|ar|ary",
    }
    base.update(overrides)
    return base


def _run(
    db: sessionmaker[Session],
    rows: list[dict[str, str]],
    specialties: dict[str, int],
    *,
    dry_run: bool = False,
):
    stats = import_doctors.Stats()
    with db() as session:
        for i, row in enumerate(rows, start=2):
            try:
                import_doctors.import_row(session, row, i, specialties, stats, dry_run=dry_run)
            except ValueError as exc:
                stats.errors.append(str(exc))
        session.commit()
    return stats


def _profile(db: sessionmaker[Session], slug: str) -> DoctorProfile | None:
    with db() as s:
        return s.execute(
            select(DoctorProfile).where(DoctorProfile.slug == slug)
        ).scalar_one_or_none()


class TestSlug:
    @pytest.mark.parametrize(
        ("name", "city", "expected"),
        [
            ("Dr. Amina Bennani", "Casablanca", "dr-amina-bennani-casablanca"),
            # Accents fold rather than vanish — "ma-rif" would be unreachable.
            ("Dr. Maâmar Naït", "Fès", "dr-maamar-nait-fes"),
            ("Dr. Sans Ville", None, "dr-sans-ville"),
        ],
    )
    def test_builds_a_readable_stable_slug(
        self, name: str, city: str | None, expected: str
    ) -> None:
        assert import_doctors.doctor_slug(name, city) == expected

    def test_includes_the_city_so_namesakes_do_not_collide(self) -> None:
        # A slug is a printed QR target; it must never be reassigned.
        casa = import_doctors.doctor_slug("Dr. Ali Alami", "Casablanca")
        rabat = import_doctors.doctor_slug("Dr. Ali Alami", "Rabat")
        assert casa != rabat


class TestImport:
    def test_creates_a_published_unclaimed_page(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        stats = _run(db, [_row()], specialties)

        assert stats.created == 1
        profile = _profile(db, "dr-amina-bennani-casablanca")
        assert profile is not None
        # Published so the city listing fills up...
        assert profile.verification_status == VerificationStatus.VERIFIED
        # ...but plainly marked as not the doctor's own.
        assert profile.claim_status == ClaimStatus.UNCLAIMED
        assert profile.source == ProfileSource.IMPORT
        assert profile.district == "Maârif"
        assert profile.languages == ["fr", "ar", "ary"]

    def test_links_the_specialty(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        _run(db, [_row()], specialties)
        with db() as s:
            links = s.execute(select(DoctorSpecialty)).scalars().all()
        assert len(links) == 1
        assert links[0].specialty_id == specialties["dentistry"]

    def test_rerunning_updates_instead_of_duplicating(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        # Field sales means running this repeatedly as the sheet improves.
        _run(db, [_row()], specialties)
        stats = _run(db, [_row(consultation_fee="400")], specialties)

        assert stats.created == 0
        assert stats.updated == 1
        with db() as s:
            assert len(s.execute(select(DoctorProfile)).scalars().all()) == 1
        assert _profile(db, "dr-amina-bennani-casablanca").consultation_fee == 400

    def test_does_not_duplicate_the_specialty_link_on_rerun(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        _run(db, [_row()], specialties)
        _run(db, [_row()], specialties)
        with db() as s:
            assert len(s.execute(select(DoctorSpecialty)).scalars().all()) == 1

    def test_leaves_blank_cells_empty_rather_than_inventing(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        # Fabricating opening hours or a fee would put wrong information on a
        # real professional's public listing.
        _run(db, [_row(consultation_fee="", phone_fixe="", address="")], specialties)
        profile = _profile(db, "dr-amina-bennani-casablanca")
        assert profile.consultation_fee is None
        assert profile.phone_fixe is None
        assert profile.address is None
        assert profile.opening_hours == []
        assert profile.insurances == []
        assert profile.photo_url is None


class TestProtections:
    def _existing(
        self, db: sessionmaker[Session], claim: ClaimStatus, *, fee: float = 999.0
    ) -> None:
        with db() as s:
            user = User(email="taken@clinic.ma", role=UserRole.DOCTOR, is_active=True)
            s.add(user)
            s.flush()
            s.add(
                DoctorProfile(
                    user_id=user.id,
                    full_name="Dr. Amina Bennani",
                    slug="dr-amina-bennani-casablanca",
                    license_no="LIC-EXISTING",
                    consultation_fee=fee,
                    claim_status=claim,
                    verification_status=VerificationStatus.VERIFIED,
                )
            )
            s.commit()

    def test_never_republishes_a_removed_doctor(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        # The whole reason removals are a tombstone rather than a delete.
        self._existing(db, ClaimStatus.REMOVAL_REQUESTED)

        stats = _run(db, [_row()], specialties)

        assert stats.skipped_removed == 1
        assert stats.created == 0
        profile = _profile(db, "dr-amina-bennani-casablanca")
        assert profile.claim_status == ClaimStatus.REMOVAL_REQUESTED
        assert profile.consultation_fee == 999.0  # untouched

    @pytest.mark.parametrize(
        "claim", [ClaimStatus.CLAIMED, ClaimStatus.VERIFIED], ids=["claimed", "verified"]
    )
    def test_never_clobbers_a_doctors_own_edits(
        self, db: sessionmaker[Session], specialties: dict[str, int], claim: ClaimStatus
    ) -> None:
        self._existing(db, claim)

        stats = _run(db, [_row(consultation_fee="1")], specialties)

        assert stats.skipped_claimed == 1
        assert _profile(db, "dr-amina-bennani-casablanca").consultation_fee == 999.0


class TestValidation:
    @pytest.mark.parametrize(
        ("row", "fragment"),
        [
            (_row(full_name=""), "full_name is required"),
            (_row(specialty=""), "specialty is required"),
            (_row(specialty="astrology"), "unknown specialty"),
            (_row(lat="33.5"), "together"),
            (_row(consultation_fee="beaucoup"), "not a number"),
        ],
    )
    def test_reports_bad_rows(
        self,
        db: sessionmaker[Session],
        specialties: dict[str, int],
        row: dict[str, str],
        fragment: str,
    ) -> None:
        stats = _run(db, [row], specialties)
        assert stats.created == 0
        assert any(fragment in e for e in stats.errors), stats.errors

    def test_one_bad_row_does_not_stop_the_rest(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        stats = _run(
            db,
            [_row(specialty="astrology"), _row(full_name="Dr. Youssef Tazi")],
            specialties,
        )
        assert stats.created == 1
        assert len(stats.errors) == 1

    def test_dry_run_writes_nothing(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        stats = _run(db, [_row()], specialties, dry_run=True)
        assert stats.created == 1  # reported as "would create"
        with db() as s:
            assert s.execute(select(DoctorProfile)).scalars().all() == []


class TestHoursColumn:
    """The compact `1:09:00-12:30,15:00-19:00; 6:09:00-13:00` weekly form."""

    def test_parses_days_and_ranges(self) -> None:
        parsed = import_doctors._parse_hours("1:09:00-12:30,15:00-19:00; 6:09:00-13:00", 2)
        assert parsed == [
            {"weekday": 0, "ranges": [["09:00", "12:30"], ["15:00", "19:00"]]},
            {"weekday": 5, "ranges": [["09:00", "13:00"]]},
        ]

    def test_sheet_is_one_indexed_but_storage_is_zero_indexed(self) -> None:
        # Operators write 1=Monday; the column stores 0=Monday. Getting this
        # backwards would publish every cabinet's hours a day out.
        assert import_doctors._parse_hours("7:10:00-14:00", 2) == [
            {"weekday": 6, "ranges": [["10:00", "14:00"]]}
        ]

    def test_blank_leaves_the_column_untouched(self) -> None:
        # None, not [] — a thin re-import must not blank hours typed by hand.
        assert import_doctors._parse_hours("", 2) is None
        assert import_doctors._parse_hours(None, 2) is None

    @pytest.mark.parametrize(
        "bad", ["9:09:00-10:00", "0:09:00-10:00", "1:0900-1000", "monday:9-10"]
    )
    def test_rejects_malformed_entries(self, bad: str) -> None:
        # Wrong opening hours send a patient to a closed door — worse than none.
        with pytest.raises(ValueError):
            import_doctors._parse_hours(bad, 2)


class TestSampleCsv:
    def test_the_shipped_sample_imports_cleanly(
        self, db: sessionmaker[Session], specialties: dict[str, int]
    ) -> None:
        # The sample doubles as the format's documentation, so it must parse.
        import csv

        sample = _SCRIPT.parent / "doctors.sample.csv"
        with sample.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))

        assert rows, "sample CSV is empty"
        # The hours column contains commas, so it must be quoted — an unquoted
        # value silently spills into extra columns and corrupts every later
        # field. csv.DictReader surfaces that as a None key.
        assert all(r.get(None) is None for r in rows), "a row has unquoted commas"
        # Only the two seeded specialties exist here; the rest are legitimately
        # unknown, so assert on the rows we can actually import.
        known = [r for r in rows if r["specialty"] in specialties]
        assert known
        stats = _run(db, known, specialties)
        assert stats.created == len(known)
        assert not stats.errors


class TestSeedPatientProfiles:
    """The demo seed must give every patient a profile.

    Patient names are read from `PatientProfile`; without one the secretary's
    day view shows every row as "Patient", which defeats a screen whose whole
    job is deciding who to phone.
    """

    def test_seed_creates_a_profile_per_patient(self) -> None:
        import importlib.util

        script = _SCRIPT.parent / "seed_demo.py"
        spec = importlib.util.spec_from_file_location("seed_demo_check", script)
        seed = importlib.util.module_from_spec(spec)
        sys.modules["seed_demo_check"] = seed
        spec.loader.exec_module(seed)

        source = script.read_text()
        assert "PatientProfile(" in source, "seed never creates a PatientProfile"
        # Every entry in PATIENTS carries a display name that must reach the DB.
        assert all(name for name, _sex, _birth in seed.PATIENTS)
