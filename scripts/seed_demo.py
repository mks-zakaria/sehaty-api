#!/usr/bin/env python
"""Sehaty demo seed — every scenario, all inside the Casablanca radius.

Idempotent: truncates all domain tables (keeps the Alembic version) and
re-inserts a full, self-consistent demo dataset so every page of every app has
something realistic to show. Written straight through the sehaty-db ORM (with
GeoAlchemy2 for the PostGIS ``geopoint``) so it needs only ``DATABASE_URL`` and
the sehaty-api virtualenv (which bundles db + core).

Run locally:
    cd sehaty-api && uv run python scripts/seed_demo.py

Run on the droplet (inside the api container, which has DATABASE_URL + deps):
    cd /opt/sehaty/sehaty-api/deploy && \
    docker compose -f docker-compose.prod.yml --env-file .env exec -T api \
        python scripts/seed_demo.py

Everything is geo-located within ~14 km of central Casablanca (33.5731, -7.5898)
so the patient "find nearest doctor" map/list is always populated.

Demo credentials (all patients/staff share one password): ``password123``.
  patient : phone +212600000001 .. (see printout)   / password123
  doctor  : dr.bennani@sehaty.ma ..                  / password123
  pharmacy: pharmacy@sehaty.ma                        / password123
  admin   : admin@sehaty.ma                           / password123
"""

from __future__ import annotations

import math
import os
import random
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select

from geoalchemy2.elements import WKTElement
from sehaty.core.security import hash_password
from sehaty.db import (
    Appointment,
    AppointmentStatus,
    Availability,
    Cabinet,
    ClinicPatient,
    Diagnosis,
    DoctorAssistant,
    DoctorProfile,
    DoctorSpecialty,
    Invoice,
    InvoiceStatus,
    Notification,
    PatientCharge,
    PatientPayment,
    PaymentMethod,
    PharmacyProduct,
    Plan,
    Prescription,
    PrescriptionItem,
    PrescriptionStatus,
    ProductKind,
    ReputationScore,
    Review,
    ReviewDirection,
    ReviewStatus,
    Sale,
    SaleItem,
    Specialty,
    Subscription,
    SubscriptionStatus,
    User,
    UserRole,
)
from sehaty.db.base import SehatyBase
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Deterministic run: same data every time (helps demos + screenshots).
random.seed(1730)

CASA = (33.5731, -7.5898)  # lat, lng of central Casablanca
PW = hash_password("password123")


def _pt(lat: float, lng: float) -> WKTElement:
    """PostGIS geography POINT — note POINT(lng lat) ordering."""
    return WKTElement(f"POINT({lng} {lat})", srid=4326)


def _jitter(km: float) -> tuple[float, float]:
    """A random point uniformly within a ``km``-radius disc of Casablanca.

    ~111 km per degree of latitude; longitude is scaled by cos(lat) (≈0.836 at
    Casablanca) so the disc stays circular on the ground.
    """
    r = km * (random.random() ** 0.5)  # sqrt → uniform over the disc area
    ang = random.random() * 2 * math.pi
    dlat = (r / 111.0) * math.cos(ang)
    dlng = (r / (111.0 * 0.836)) * math.sin(ang)
    return CASA[0] + dlat, CASA[1] + dlng


# Casablanca neighbourhoods used for addresses (paired with jittered coords).
NEIGHBORHOODS = [
    "Maârif", "Ain Diab", "Gauthier", "Anfa", "Bourgogne", "Sidi Maârouf",
    "Hay Hassani", "Oulfa", "Ain Sebaâ", "Sidi Bernoussi", "Bouskoura",
    "Derb Sultan", "Racine", "Palmier", "CIL", "Belvédère",
]

NOW = datetime.now(UTC)


def _reset(session: Session) -> None:
    """Truncate every domain table (keep alembic_version), reset identities."""
    tables = [
        t.name for t in reversed(SehatyBase.metadata.sorted_tables)
        if t.name != "alembic_version"
    ]
    session.execute(
        text(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
    )


def _seed_specialties(session: Session) -> dict[str, Specialty]:
    rows = [
        ("generalist", "General practitioner", "Médecin généraliste", "طبيب عام", "طبيب ديال العام"),
        ("cardiology", "Cardiologist", "Cardiologue", "طبيب قلب", "طبيب ديال القلب"),
        ("dermatology", "Dermatologist", "Dermatologue", "طبيب جلدية", "طبيب ديال الجلد"),
        ("pediatrics", "Pediatrician", "Pédiatre", "طبيب أطفال", "طبيب ديال الدراري"),
        ("dentistry", "Dentist", "Dentiste", "طبيب أسنان", "طبيب ديال السنان"),
        ("gynecology", "Gynecologist", "Gynécologue", "طبيب نساء", "طبيب ديال العيالات"),
        ("ophthalmology", "Ophthalmologist", "Ophtalmologue", "طبيب عيون", "طبيب ديال العينين"),
        ("otolaryngology", "ENT", "ORL", "طبيب أنف وأذن", "طبيب ديال الأذن"),
        ("psychiatry", "Psychiatrist", "Psychiatre", "طبيب نفسي", "طبيب ديال العقل"),
        ("orthopedics", "Orthopedist", "Orthopédiste", "طبيب عظام", "طبيب ديال العظام"),
    ]
    out: dict[str, Specialty] = {}
    for slug, en, fr, ar, ary in rows:
        sp = Specialty(slug=slug, name_en=en, name_fr=fr, name_ar=ar, name_ary=ary)
        session.add(sp)
        out[slug] = sp
    session.flush()
    return out


def _seed_plans(session: Session) -> list[Plan]:
    plans = [
        Plan(code="basic", name="Basic", price_month=299.0, currency="MAD", is_active=True),
        Plan(code="pro", name="Pro", price_month=599.0, currency="MAD", is_active=True),
        Plan(code="clinic", name="Clinic", price_month=999.0, currency="MAD", is_active=True),
    ]
    session.add_all(plans)
    session.flush()
    return plans


# (email, display name, [specialty slugs], fee, verification, sub-status, languages)
DOCTORS = [
    ("dr.bennani@sehaty.ma", "Dr. Amina Bennani", ["dentistry", "orthodontics_alias"], 350, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    ("dr.tazi@sehaty.ma", "Dr. Youssef Tazi", ["cardiology"], 450, "VERIFIED", "ACTIVE", ["fr", "ar", "en"]),
    ("dr.alaoui@sehaty.ma", "Dr. Salma Alaoui", ["dermatology"], 300, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    ("dr.chraibi@sehaty.ma", "Dr. Karim Chraibi", ["pediatrics"], 250, "VERIFIED", "TRIALING", ["fr", "ar"]),
    ("dr.fassi@sehaty.ma", "Dr. Nadia Fassi", ["gynecology"], 400, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    ("dr.idrissi@sehaty.ma", "Dr. Hamza Idrissi", ["generalist"], 150, "VERIFIED", "ACTIVE", ["fr", "ar", "ary"]),
    ("dr.berrada@sehaty.ma", "Dr. Leila Berrada", ["ophthalmology"], 350, "VERIFIED", "PAST_DUE", ["fr", "ar"]),
    ("dr.saidi@sehaty.ma", "Dr. Omar Saidi", ["dentistry"], 320, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    ("dr.mansouri@sehaty.ma", "Dr. Fatima Mansouri", ["orthopedics"], 380, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    ("dr.kabbaj@sehaty.ma", "Dr. Rachid Kabbaj", ["otolaryngology"], 300, "VERIFIED", "ACTIVE", ["fr", "ar"]),
    # Accreditation queue (admin): still PENDING verification.
    ("dr.nouri@sehaty.ma", "Dr. Sanaa Nouri", ["psychiatry"], 500, "PENDING", "TRIALING", ["fr", "ar"]),
    ("dr.hakimi@sehaty.ma", "Dr. Bilal Hakimi", ["generalist"], 180, "PENDING", "TRIALING", ["fr", "ar"]),
    # Rejected accreditation.
    ("dr.rejected@sehaty.ma", "Dr. Test Rejected", ["generalist"], 200, "REJECTED", "CANCELLED", ["fr"]),
]

PATIENTS = [
    ("Mehdi Alami", "male", 1990), ("Zineb Ouazzani", "female", 1985),
    ("Khalid Sabri", "male", 1978), ("Hajar Lahlou", "female", 1995),
    ("Anas Rami", "male", 2001), ("Imane Belkadi", "female", 1988),
    ("Yassine Cherkaoui", "male", 1972), ("Sofia Amrani", "female", 1993),
    ("Reda Benjelloun", "male", 1980), ("Nawal Sekkat", "female", 1998),
    ("Amine Doukkali", "male", 1965), ("Loubna Hilali", "female", 1991),
]


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    engine = create_engine(url, future=True)
    Factory = sessionmaker(bind=engine, expire_on_commit=False)

    with Factory() as session:
        _reset(session)
        specs = _seed_specialties(session)
        plans = _seed_plans(session)
        basic, pro, clinic = plans

        # -- Doctors -------------------------------------------------------
        doctors: list[User] = []
        doctor_profiles: dict[int, DoctorProfile] = {}
        for i, (email, name, slugs, fee, vstatus, substatus, langs) in enumerate(DOCTORS):
            lat, lng = _jitter(13.0)
            hood = NEIGHBORHOODS[i % len(NEIGHBORHOODS)]
            u = User(
                email=email, phone=f"+21252{i:07d}", password_hash=PW,
                role=UserRole.DOCTOR, is_active=True, consented_at=NOW,
            )
            session.add(u)
            session.flush()
            doctors.append(u)
            slug = email.split("@")[0].replace(".", "-")
            prof = DoctorProfile(
                user_id=u.id, full_name=name, slug=slug,
                license_no=f"CAS-{10000 + i}",
                bio=f"{name} — cabinet à {hood}, Casablanca. Consultations sur rendez-vous.",
                address=f"Rue {random.randint(1, 120)}, {hood}, Casablanca",
                city="Casablanca", geopoint=_pt(lat, lng),
                consultation_fee=float(fee), verification_status=vstatus,
                referral_code=f"REF{u.id:04d}", is_staff=False, languages=langs,
                timezone="Africa/Casablanca",
            )
            session.add(prof)
            doctor_profiles[u.id] = prof
            # Specialties (ignore the aliased extra slug used only for readability).
            for s in slugs:
                if s in specs:
                    session.add(DoctorSpecialty(doctor_id=u.id, specialty_id=specs[s].id))
            # Availability: Mon–Fri 09:00–13:00 & 15:00–18:00, 30-min slots.
            for wd in range(0, 5):
                session.add(Availability(doctor_id=u.id, weekday=wd,
                            start_time=time(9, 0), end_time=time(13, 0), slot_minutes=30))
                session.add(Availability(doctor_id=u.id, weekday=wd,
                            start_time=time(15, 0), end_time=time(18, 0), slot_minutes=30))
            # Cabinet.
            session.add(Cabinet(owner_doctor_id=u.id, name=f"Cabinet {name.split()[-1]}",
                        address=prof.address, is_active=True,
                        waiting_room_count=random.randint(0, 4), waiting_alert_threshold=5))
            # Subscription + invoices (verified doctors only).
            if vstatus == "VERIFIED":
                plan = random.choice(plans)
                sub = Subscription(
                    doctor_id=u.id, plan_id=plan.id,
                    status=SubscriptionStatus(substatus),
                    current_period_start=NOW - timedelta(days=10),
                    current_period_end=NOW + timedelta(days=20),
                )
                session.add(sub)
                session.flush()
                # A paid invoice last month.
                session.add(Invoice(doctor_id=u.id, subscription_id=sub.id,
                            amount=plan.price_month, currency="MAD",
                            status=InvoiceStatus.PAID, issued_at=NOW - timedelta(days=40),
                            due_at=NOW - timedelta(days=25), paid_at=NOW - timedelta(days=30)))
                # Current invoice: OPEN (overdue for the PAST_DUE doctor).
                overdue = substatus == "PAST_DUE"
                session.add(Invoice(doctor_id=u.id, subscription_id=sub.id,
                            amount=plan.price_month, currency="MAD",
                            status=InvoiceStatus.OPEN,
                            issued_at=NOW - timedelta(days=10),
                            due_at=NOW - timedelta(days=3 if overdue else -12),
                            paid_at=None))
        session.flush()

        verified_doctors = [d for d, spec in zip(doctors, DOCTORS) if spec[4] == "VERIFIED"]

        # -- Patients ------------------------------------------------------
        patients: list[User] = []
        for i, (name, sex, birth) in enumerate(PATIENTS, start=1):
            u = User(email=f"patient{i}@example.ma", phone=f"+21260000{i:04d}",
                     password_hash=PW, role=UserRole.PATIENT, is_active=True,
                     consented_at=NOW if i % 4 else None)
            session.add(u)
            session.flush()
            patients.append(u)
        session.flush()

        # -- Register rows, appointments, reviews, clinical ---------------
        _seed_encounters(session, verified_doctors, doctor_profiles, patients, specs)

        # -- Debt ledger scenarios (the braces case) ----------------------
        dentists = [d for d, spec in zip(doctors, DOCTORS)
                    if "dentistry" in spec[2] and spec[4] == "VERIFIED"]
        _seed_ledger(session, dentists, patients)

        # -- Pharmacy ------------------------------------------------------
        _seed_pharmacy(session)

        # -- Assistant + Admin --------------------------------------------
        assistant = User(email="assistant@sehaty.ma", phone="+212533000001",
                         password_hash=PW, role=UserRole.ASSISTANT, is_active=True)
        session.add(assistant)
        session.flush()
        session.add(DoctorAssistant(doctor_id=verified_doctors[0].id,
                    assistant_id=assistant.id, is_active=True))
        session.add(User(email="admin@sehaty.ma", phone="+212533000009",
                    password_hash=PW, role=UserRole.ADMIN, is_active=True))

        # -- Notifications -------------------------------------------------
        for p in patients[:6]:
            session.add(Notification(user_id=p.id, kind="APPOINTMENT_CONFIRMED",
                        message="Votre rendez-vous a été confirmé.", entity="appointment",
                        is_read=False))
        for d in verified_doctors[:5]:
            session.add(Notification(user_id=d.id, kind="NEW_BOOKING",
                        message="Nouvelle demande de rendez-vous.", entity="appointment",
                        is_read=False))

        session.commit()
        _print_summary(session)


def _seed_encounters(session, doctors, profiles, patients, specs) -> None:
    """Appointments across every status + register rows + reviews + reputation."""
    review_pool: list[tuple[int, int, int]] = []  # (doctor_id, patient_id, appt_id)

    for d in doctors:
        # Register: 4 app-linked patients + 2 walk-ins per doctor.
        booked = random.sample(patients, 4)
        register: list[ClinicPatient] = []
        for p in booked:
            cp = ClinicPatient(doctor_id=d.id, user_id=p.id,
                               full_name=_name_of(p), phone=p.phone,
                               email=p.email, sex=random.choice(["male", "female"]),
                               birth_year=random.randint(1965, 2005),
                               tags=random.choice([[], ["chronic"], ["vip"], ["new"]]),
                               created_by=d.id)
            session.add(cp)
            register.append(cp)
        for w in range(2):
            cp = ClinicPatient(doctor_id=d.id, user_id=None,
                               full_name=random.choice(
                                   ["Walk-in Rachid", "Walk-in Souad", "Walk-in Brahim"]),
                               phone=f"+2126{random.randint(10000000, 99999999)}",
                               sex=random.choice(["male", "female"]),
                               birth_year=random.randint(1960, 2010),
                               notes="Patient sans compte (walk-in).", created_by=d.id)
            session.add(cp)
            register.append(cp)
        session.flush()

        # Past COMPLETED (reviewable), staggered so they never overlap.
        base = NOW - timedelta(days=30)
        for k in range(4):
            cp = register[k]
            start = base + timedelta(days=k * 3, hours=k % 3)
            appt = Appointment(patient_id=cp.user_id or patients[0].id, doctor_id=d.id,
                               clinic_patient_id=cp.id, start_at=start,
                               end_at=start + timedelta(minutes=30),
                               status=AppointmentStatus.COMPLETED,
                               reason=random.choice(["Contrôle", "Douleur", "Suivi", "Consultation"]),
                               notes="Consultation terminée.",
                               consultation_started_at=start,
                               consultation_ended_at=start + timedelta(minutes=25))
            session.add(appt)
            session.flush()
            if cp.user_id:
                review_pool.append((d.id, cp.user_id, appt.id))
            # A diagnosis on some completed visits.
            if k % 2 == 0:
                session.add(Diagnosis(doctor_id=d.id, clinic_patient_id=cp.id,
                            appointment_id=appt.id,
                            label=random.choice(["Hypertension", "Caries", "Rhinite", "Lombalgie"]),
                            icd10=random.choice(["I10", "K02", "J30", "M54"]),
                            diagnosed_at=start))

        # Past NO_SHOW and CANCELLED.
        ns_start = NOW - timedelta(days=12, hours=2)
        session.add(Appointment(patient_id=register[0].user_id or patients[0].id,
                    doctor_id=d.id, clinic_patient_id=register[0].id, start_at=ns_start,
                    end_at=ns_start + timedelta(minutes=30),
                    status=AppointmentStatus.NO_SHOW, reason="Absent"))
        cx_start = NOW - timedelta(days=8, hours=4)
        session.add(Appointment(patient_id=register[1].user_id or patients[0].id,
                    doctor_id=d.id, clinic_patient_id=register[1].id, start_at=cx_start,
                    end_at=cx_start + timedelta(minutes=30),
                    status=AppointmentStatus.CANCELLED, reason="Annulé par le patient"))

        # Today: one CHECKED_IN (cabinet waiting room) + one IN_PROGRESS.
        t0 = NOW.replace(hour=9, minute=0, second=0, microsecond=0)
        session.add(Appointment(patient_id=register[2].user_id or patients[0].id,
                    doctor_id=d.id, clinic_patient_id=register[2].id, start_at=t0,
                    end_at=t0 + timedelta(minutes=30),
                    status=AppointmentStatus.CHECKED_IN, reason="Contrôle"))
        t1 = t0 + timedelta(minutes=30)
        session.add(Appointment(patient_id=register[3].user_id or patients[0].id,
                    doctor_id=d.id, clinic_patient_id=register[3].id, start_at=t1,
                    end_at=t1 + timedelta(minutes=30),
                    status=AppointmentStatus.IN_PROGRESS, reason="Consultation",
                    consultation_started_at=NOW))

        # Future CONFIRMED (2) + REQUESTED (2), spaced so no per-doctor overlap.
        fut = (NOW + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
        for k in range(2):
            s = fut + timedelta(days=k, minutes=0)
            session.add(Appointment(patient_id=booked[k].id, doctor_id=d.id,
                        clinic_patient_id=register[k].id, start_at=s,
                        end_at=s + timedelta(minutes=30),
                        status=AppointmentStatus.CONFIRMED, reason="Rendez-vous confirmé"))
        for k in range(2):
            s = fut + timedelta(days=4 + k, minutes=0)
            session.add(Appointment(patient_id=booked[k + 1].id, doctor_id=d.id,
                        clinic_patient_id=register[k + 1].id, start_at=s,
                        end_at=s + timedelta(minutes=30),
                        status=AppointmentStatus.REQUESTED, reason="Demande de rendez-vous"))
    session.flush()

    # Reviews across statuses + reputation aggregation.
    agg: dict[int, list[int]] = {}
    for idx, (doctor_id, patient_id, appt_id) in enumerate(review_pool):
        # Most PUBLISHED; a few PENDING (moderation queue); one FLAGGED.
        if idx % 11 == 5:
            status, stars = ReviewStatus.PENDING, random.randint(3, 5)
        elif idx % 17 == 3:
            status, stars = ReviewStatus.FLAGGED, random.randint(1, 2)
        else:
            status, stars = ReviewStatus.PUBLISHED, random.randint(3, 5)
        comment = random.choice([
            "Médecin à l'écoute, je recommande.", "Très professionnel.",
            "Cabinet propre, peu d'attente.", "Bonne prise en charge.",
            "Explications claires.", "",
        ])
        rev = Review(author_id=patient_id, target_id=doctor_id, appointment_id=appt_id,
                     direction=ReviewDirection.PATIENT_ON_DOCTOR, stars=stars,
                     comment=comment or None, status=status,
                     reply="Merci pour votre retour." if (idx % 5 == 0 and status == ReviewStatus.PUBLISHED) else None,
                     reply_at=NOW if idx % 5 == 0 else None)
        session.add(rev)
        if status == ReviewStatus.PUBLISHED:
            agg.setdefault(doctor_id, []).append(stars)
    session.flush()
    for doctor_id, stars_list in agg.items():
        session.add(ReputationScore(user_id=doctor_id,
                    avg_stars=round(sum(stars_list) / len(stars_list), 2),
                    review_count=len(stars_list), updated_at=NOW))
    session.flush()


def _seed_ledger(session, dentists, patients) -> None:
    """Every debt scenario: unpaid, partial, settled, multi-charge, over time."""
    if not dentists:
        return
    d = dentists[0]
    # Fetch this dentist's register rows to attach charges to real patients.
    register = session.execute(
        select(ClinicPatient).where(ClinicPatient.doctor_id == d.id)
    ).scalars().all()
    if len(register) < 4:
        return

    def charge(cp, label, total, payments, note=None):
        c = PatientCharge(doctor_id=d.id, clinic_patient_id=cp.id, label=label,
                          total_amount=float(total), currency="MAD", note=note,
                          created_by=d.id)
        session.add(c)
        session.flush()
        day = NOW - timedelta(days=60)
        for amt, method in payments:
            day = day + timedelta(days=15)
            session.add(PatientPayment(charge_id=c.id, amount=float(amt),
                        method=PaymentMethod(method), paid_at=day, created_by=d.id))
        return c

    # 1) Braces, partially paid: 8000, down 3000 + 2000 → 3000 outstanding.
    charge(register[0], "Appareil dentaire (bagues)", 8000,
           [(3000, "CASH"), (2000, "CARD")], note="Traitement 18 mois.")
    # 2) Braces, fully settled: 6000 in three instalments.
    charge(register[1], "Appareil dentaire (bagues)", 6000,
           [(2000, "CASH"), (2000, "CASH"), (2000, "TRANSFER")])
    # 3) Braces, nothing paid yet: 10000 outstanding.
    charge(register[2], "Appareil dentaire (bagues)", 10000, [], note="Début du traitement.")
    # 4) Cleaning, paid same day.
    charge(register[3], "Détartrage", 400, [(400, "CASH")])
    # 5) Multi-charge patient (rollup): register[0] also owes an extraction.
    charge(register[0], "Extraction dent de sagesse", 1200, [(200, "CASH")])
    # 6) Root canal, half paid.
    charge(register[1], "Traitement de canal", 1500, [(750, "CARD")])
    session.flush()


def _seed_pharmacy(session) -> None:
    pharm = User(email="pharmacy@sehaty.ma", phone="+212533000005",
                 password_hash=PW, role=UserRole.PHARMACY, is_active=True)
    session.add(pharm)
    session.flush()
    products = [
        ("6111000000017", "Doliprane 1000mg", ProductKind.MEDICINE, 22.50, 120, 20),
        ("6111000000024", "Efferalgan 500mg", ProductKind.MEDICINE, 18.00, 8, 15),   # low
        ("6111000000031", "Amoxicilline 500mg", ProductKind.MEDICINE, 45.00, 60, 20),
        ("6111000000048", "Ventoline", ProductKind.MEDICINE, 38.00, 5, 10),           # low
        ("6111000000055", "Smecta", ProductKind.MEDICINE, 30.00, 40, 15),
        ("6111000000062", "Vitamine C", ProductKind.MEDICINE, 25.00, 200, 30),
        ("6111000000079", "Crème solaire SPF50", ProductKind.COSMETIC, 89.00, 25, 10),
        ("6111000000086", "Shampoing dermato", ProductKind.COSMETIC, 65.00, 3, 8),    # low
        ("6111000000093", "Sérum hydratant", ProductKind.COSMETIC, 120.00, 18, 6),
        ("6111000000109", "Gel hydroalcoolique", ProductKind.MEDICINE, 15.00, 300, 40),
    ]
    prods = []
    for barcode, name, kind, price, qty, low in products:
        p = PharmacyProduct(pharmacy_id=pharm.id, barcode=barcode, name=name,
                            kind=kind, price=price, quantity=qty, low_threshold=low,
                            is_active=True)
        session.add(p)
        prods.append(p)
    session.flush()
    # A few past sales for the sales report.
    for day_off in (1, 2, 5, 9):
        picks = random.sample(prods, random.randint(1, 3))
        sale = Sale(pharmacy_id=pharm.id, sold_at=NOW - timedelta(days=day_off), total=0.0)
        session.add(sale)
        session.flush()
        total = 0.0
        for pr in picks:
            q = random.randint(1, 3)
            line = round(pr.price * q, 2)
            total += line
            session.add(SaleItem(sale_id=sale.id, product_id=pr.id, name=pr.name,
                        quantity=q, unit_price=pr.price, line_total=line))
        sale.total = round(total, 2)
    session.flush()


def _name_of(user: User) -> str:
    idx = int(user.email.replace("patient", "").split("@")[0]) - 1
    return PATIENTS[idx][0] if 0 <= idx < len(PATIENTS) else user.email


def _print_summary(session: Session) -> None:
    def n(model):
        return session.execute(select(func.count()).select_from(model)).scalar_one()
    print("\n✅ Casablanca demo seed complete\n" + "-" * 40)
    print(f"  specialties        {n(Specialty)}")
    print(f"  doctors            {session.execute(select(func.count()).select_from(User).where(User.role == UserRole.DOCTOR)).scalar_one()}")
    print(f"  patients           {session.execute(select(func.count()).select_from(User).where(User.role == UserRole.PATIENT)).scalar_one()}")
    print(f"  appointments       {n(Appointment)}")
    print(f"  reviews            {n(Review)}")
    print(f"  ledger charges     {n(PatientCharge)}")
    print(f"  ledger payments    {n(PatientPayment)}")
    print(f"  pharmacy products  {n(PharmacyProduct)}")
    print(f"  sales              {n(Sale)}")
    print("-" * 40)
    print("  Login (password123):")
    print("    patient  +212600000001 .. +212600000012")
    print("    doctor   dr.bennani@sehaty.ma (dentist w/ debt ledger)")
    print("    pharmacy pharmacy@sehaty.ma")
    print("    admin    admin@sehaty.ma")
    print("    assistant assistant@sehaty.ma")
    print()


if __name__ == "__main__":
    main()
