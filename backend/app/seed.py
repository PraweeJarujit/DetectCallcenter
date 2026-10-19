"""
สร้างข้อมูลตั้งต้น/ตัวอย่างให้ระบบ (idempotent — รันซ้ำได้ ไม่สร้างซ้ำ)

    python -m app.seed

- scam_categories : เติมให้ครบเสมอ (ปกติ migration 0001 ใส่ไว้แล้ว)
- demo data       : เฉพาะเมื่อ SEED_DEMO_DATA=true (ค่าเริ่มต้น) — ปิดใน production!
    admin     / Admin1234   ผู้ดูแลระบบ
    demo      / demo1234    สมาชิก Premium (มีอายุ 30 วันนับจากวันที่ seed)
    free.demo / demo1234    สมาชิกฟรี
  + เบอร์ blacklist ตัวอย่าง, report, call log ย้อนหลัง 7 วัน ให้ dashboard มีข้อมูล
"""
import logging
import random
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models import BlacklistNumber, CallLog, EmergencyContact, Payment, Report, ScamCategory, User
from app.models._common import utcnow
from app.models.blacklist_number import status_from_score
from app.models.call_log import CallSource
from app.models.payment import PaymentStatus
from app.models.scam_category import DEFAULT_CATEGORIES
from app.models.user import UserRole

logger = logging.getLogger("app.seed")

DEMO_USERS = [
    ("admin", "admin@example.com", "Admin1234", "ผู้ดูแลระบบ", UserRole.admin),
    ("demo", "demo@example.com", "demo1234", "สมชาย ใจดี", UserRole.member),
    ("free.demo", "free@example.com", "demo1234", "วิภา รักษ์ดี", UserRole.member),
]


def seed_categories(db: Session) -> int:
    existing = set(db.scalars(select(ScamCategory.code)).all())
    added = 0
    for code, name in DEFAULT_CATEGORIES:
        if code not in existing:
            db.add(ScamCategory(code=code, name=name))
            added += 1
    db.commit()
    return added


def _add_premium_demo_extras(db: Session, user: User) -> None:
    user.premium_until = utcnow() + timedelta(days=30)
    user.auto_renew = True
    db.add_all([
        EmergencyContact(user_id=user.id, name="คุณแม่", phone_number="0815551234"),
        EmergencyContact(user_id=user.id, name="น้องสาว", phone_number="0897771234"),
        Payment(user_id=user.id, amount_baht=settings.PREMIUM_PRICE_BAHT, status=PaymentStatus.paid,
                provider="mock", provider_ref=f"VGSEED{user.id.hex[:8].upper()}", method="promptpay",
                period_start=utcnow(), period_end=user.premium_until, expires_at=utcnow(), paid_at=utcnow()),
    ])


def ensure_demo_accounts(db: Session) -> list[str]:
    """เพิ่มบัญชีทดลองที่ยังไม่มี (กรณีฐานข้อมูลเดิมมีผู้ใช้อยู่แล้ว เช่น อัปเกรดจากเวอร์ชันเก่า) ไม่แตะบัญชีอื่น"""
    existing = set(db.scalars(select(User.username)).all())
    taken_emails = set(db.scalars(select(User.email)).all())
    added = []
    for username, email, pw, name, role in DEMO_USERS:
        if username in existing:
            continue
        if email in taken_emails:
            email = f"{username}.demo@example.com"
        u = User(username=username, email=email, hashed_password=hash_password(pw), full_name=name, role=role)
        db.add(u)
        db.flush()
        if username == "demo":
            _add_premium_demo_extras(db, u)
        added.append(username)
    db.commit()
    return added


def seed_demo(db: Session, rng: random.Random | None = None) -> bool:
    if db.scalar(select(func.count()).select_from(User)):
        return False  # มีผู้ใช้แล้ว ไม่ทับข้อมูลจริง
    rng = rng or random.Random(42)

    users = []
    for username, email, pw, name, role in DEMO_USERS:
        u = User(username=username, email=email, hashed_password=hash_password(pw), full_name=name, role=role)
        db.add(u)
        users.append(u)
    db.flush()
    officer = users[1]
    _add_premium_demo_extras(db, officer)

    categories = db.scalars(select(ScamCategory)).all()
    now = utcnow()
    numbers = []
    for i in range(40):
        phone = f"0{rng.choice([6, 8, 9])}{rng.randint(10_000_000, 99_999_999)}"
        score = rng.choice([55, 62, 70, 81, 87, 90, 95])
        n_reports = rng.randint(1, 4)
        record = BlacklistNumber(
            phone_number=phone, risk_score=score, report_count=n_reports, status=status_from_score(score),
            first_reported_at=now - timedelta(days=rng.randint(5, 60)),
        )
        db.add(record)
        numbers.append(record)
        for _ in range(n_reports):
            db.add(Report(
                blacklist_number=record, reporter=rng.choice(users[1:]), risk_score=score,
                note="ข้อมูลตัวอย่าง (seed)", categories=rng.sample(categories, k=rng.randint(1, 2)),
                created_at=now - timedelta(days=rng.randint(0, 5), hours=rng.randint(0, 23)),
            ))

    # call log ย้อนหลัง 7 วัน ~80-140 สาย/วัน ให้กราฟแนวโน้มมีชีวิต
    for day in range(7):
        for _ in range(rng.randint(80, 140)):
            score = rng.choices([rng.randint(0, 49), rng.randint(50, 79), rng.randint(80, 99)], [6, 2, 2])[0]
            phone = rng.choice(numbers).phone_number if score >= 50 and rng.random() < 0.5 \
                else f"08{rng.randint(10_000_000, 99_999_999)}"
            source = rng.choice([CallSource.number_check, CallSource.audio, CallSource.text])
            db.add(CallLog(
                phone_number=phone, user_id=rng.choice([None, officer.id]), risk_score=score,
                status=status_from_score(score),
                # "เสียงสังเคราะห์" มีความหมายเฉพาะผลตรวจไฟล์เสียง
                is_synthetic_voice=source == CallSource.audio and score >= 80 and rng.random() < 0.7,
                source=source,
                created_at=now - timedelta(days=day, minutes=rng.randint(0, 60 * 20)),
            ))
    db.commit()
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with SessionLocal() as db:
        added = seed_categories(db)
        logger.info("scam_categories: added %d", added)
        if settings.SEED_DEMO_DATA:
            created = seed_demo(db)
            if created:
                logger.info("demo data: created")
            else:
                logger.info("demo data: skipped (users already exist); demo accounts added: %s",
                            ensure_demo_accounts(db) or "none")
        else:
            logger.info("demo data: disabled (SEED_DEMO_DATA=false)")


if __name__ == "__main__":
    main()
