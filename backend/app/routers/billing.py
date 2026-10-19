"""
Router: สมาชิก Premium 59 บาท/เดือน + บัญชีของฉัน + ติดต่อเรา + หน้าแอดมิน

  GET  /billing/plans                     แพ็กเกจทั้งหมด (ไม่ต้อง login)
  GET  /billing/me                        สถานะสมาชิก + โควตาที่ใช้ไปวันนี้
  POST /billing/checkout                  สร้างรายการชำระเงิน (หมดอายุใน 15 นาที)
  POST /billing/checkout/{id}/confirm     ยืนยันการชำระ — เฉพาะโหมดทดลอง (PAYMENT_PROVIDER=mock)
  POST /billing/cancel                    ยกเลิกการต่ออายุอัตโนมัติ (ใช้ได้จนหมดรอบ)
  GET  /billing/payments                  ประวัติการชำระ
  GET  /me/summary                        ตัวเลขสรุปในหน้าแรกของผู้ใช้
  GET  /ai/status                         สถานะโมเดล AI + ผลวัดความแม่นยำ (แสดงบนหน้าเว็บ)
  POST /contact                           ฟอร์มติดต่อเรา (ไม่ต้อง login)
  GET/PUT /admin/contact-messages         กล่องข้อความของ admin
  GET  /admin/overview                    ตัวเลขภาพรวมสำหรับ admin

ระบบชำระเงินตอนนี้เป็น "โหมดทดลอง": ไม่มีการตัดเงินจริง เมื่อเปิดบัญชี payment gateway แล้ว
ให้เปลี่ยน /confirm เป็น webhook ที่ gateway เรียกกลับ (โครงข้อมูลใน payments รองรับแล้ว)
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError, PermissionDeniedError, TooManyRequestsError
from app.core.rate_limit import SlidingWindowLimiter
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.blacklist_number import BlacklistNumber
from app.models.call_log import CallLog
from app.models.contact_message import ContactMessage, ContactStatus
from app.models.emergency_contact import EmergencyContact
from app.models.payment import Payment, PaymentStatus
from app.models.report import Report
from app.models.user import User, UserRole
from app.routers.calls import local_midnight_utc, local_today
from app.routers.detect import number_checks_today
from app.schemas.billing import (
    AccountSummary,
    AdminOverview,
    BillingStatus,
    CheckoutOut,
    CheckoutRequest,
    ContactMessageOut,
    ContactRequest,
    ContactUpdate,
    PaginatedContactMessages,
    PaymentOut,
    PlanOut,
    Usage,
)
from app.services import ai_client

router = APIRouter(tags=["billing"])
logger = logging.getLogger("app.billing")

contact_limiter = SlidingWindowLimiter(settings.CONTACT_MAX_PER_HOUR, 3600)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:  # SQLite คืนค่าแบบไม่มี timezone
        return dt.replace(tzinfo=timezone.utc)
    return dt


def plans() -> list[PlanOut]:
    free = settings.FREE_DAILY_NUMBER_CHECKS
    return [
        PlanOut(code="free", name="ฟรี", price_baht=0, period="ตลอดไป", features=[
            f"ตรวจเบอร์โทรกับฐานข้อมูลเบอร์มิจฉาชีพ {free} ครั้งต่อวัน",
            "ค้นหาและดูรายชื่อเบอร์ที่ถูกแจ้ง",
            "แจ้งเบอร์มิจฉาชีพให้คนอื่นรู้",
        ]),
        PlanOut(code="premium", name="Premium", price_baht=settings.PREMIUM_PRICE_BAHT, period="ต่อเดือน", features=[
            "ตรวจเบอร์โทรได้ไม่จำกัด",
            "AI ตรวจไฟล์เสียงว่าเป็นเสียงสังเคราะห์หรือไม่",
            "AI ตรวจข้อความ SMS / LINE ว่าเข้าข่ายหลอกลวงไหม",
            "แจ้งผู้ติดต่อฉุกเฉินเมื่อพบความเสี่ยงสูง",
            "ประวัติการตรวจย้อนหลังทั้งหมด",
        ]),
    ]


def billing_status(db: Session, user: User) -> BillingStatus:
    return BillingStatus(
        plan=user.plan, is_premium=user.is_premium, premium_until=user.premium_until, auto_renew=user.auto_renew,
        price_baht=settings.PREMIUM_PRICE_BAHT,
        usage=Usage(number_checks_today=number_checks_today(db, user), free_daily_limit=settings.FREE_DAILY_NUMBER_CHECKS),
    )


# ======================= Billing =======================

@router.get("/billing/plans", response_model=list[PlanOut])
def list_plans():
    return plans()


@router.get("/billing/me", response_model=BillingStatus)
def my_billing(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return billing_status(db, current_user)


@router.post("/billing/checkout", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
def create_checkout(
    payload: CheckoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == UserRole.admin:
        raise BadRequestError("บัญชีผู้ดูแลระบบใช้ฟีเจอร์ Premium ได้อยู่แล้ว")
    now = _now()
    # ใช้รายการที่ยังรอชำระและยังไม่หมดอายุซ้ำ กันกดซ้ำแล้วได้หลายรายการ
    pending = db.scalar(
        select(Payment).where(Payment.user_id == current_user.id, Payment.status == PaymentStatus.pending)
        .order_by(Payment.created_at.desc()).limit(1)
    )
    if pending is not None and _aware(pending.expires_at) > now and pending.method == payload.method:
        payment = pending
    else:
        if pending is not None:
            pending.status = PaymentStatus.expired
        payment = Payment(
            user_id=current_user.id, amount_baht=settings.PREMIUM_PRICE_BAHT, provider=settings.PAYMENT_PROVIDER,
            provider_ref=f"VG{now:%y%m%d}{secrets.token_hex(4).upper()}", method=payload.method,
            expires_at=now + timedelta(minutes=settings.CHECKOUT_EXPIRE_MINUTES),
        )
        db.add(payment)
        db.commit()
        db.refresh(payment)
    return CheckoutOut(
        payment_id=payment.id, amount_baht=payment.amount_baht, method=payment.method, reference=payment.provider_ref,
        provider=payment.provider, expires_at=payment.expires_at, is_test_mode=payment.provider == "mock",
    )


@router.post("/billing/checkout/{payment_id}/confirm", response_model=BillingStatus)
def confirm_checkout(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if settings.PAYMENT_PROVIDER != "mock":
        raise PermissionDeniedError("การยืนยันด้วยตัวเองใช้ได้เฉพาะโหมดทดลอง")
    payment = db.get(Payment, payment_id)
    if payment is None or payment.user_id != current_user.id:
        raise NotFoundError("ไม่พบรายการชำระเงินนี้")
    if payment.status != PaymentStatus.pending:
        raise BadRequestError("รายการนี้ชำระหรือยกเลิกไปแล้ว")
    now = _now()
    if _aware(payment.expires_at) <= now:
        payment.status = PaymentStatus.expired
        db.commit()
        raise BadRequestError("รายการชำระเงินหมดอายุแล้ว กรุณาเริ่มใหม่")

    # ต่ออายุต่อจากวันหมดอายุเดิม (ถ้ายังไม่หมด) ไม่ทับวันที่เหลืออยู่
    start = max(now, _aware(current_user.premium_until) or now)
    payment.status = PaymentStatus.paid
    payment.paid_at = now
    payment.period_start = start
    payment.period_end = start + timedelta(days=settings.PREMIUM_PERIOD_DAYS)
    current_user.premium_until = payment.period_end
    current_user.auto_renew = True
    db.commit()
    db.refresh(current_user)
    logger.info("premium activated user=%s until=%s ref=%s", current_user.username, payment.period_end, payment.provider_ref)
    return billing_status(db, current_user)


@router.post("/billing/cancel", response_model=BillingStatus)
def cancel_subscription(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not current_user.auto_renew:
        raise BadRequestError("ไม่ได้เปิดการต่ออายุอัตโนมัติอยู่")
    current_user.auto_renew = False
    db.commit()
    db.refresh(current_user)
    return billing_status(db, current_user)


@router.get("/billing/payments", response_model=list[PaymentOut])
def my_payments(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # ใช้ IDX-10 (user_id, created_at DESC)
    return db.scalars(
        select(Payment).where(Payment.user_id == current_user.id).order_by(Payment.created_at.desc()).limit(24)
    ).all()


# ======================= Account =======================

@router.get("/me/summary", response_model=AccountSummary)
def my_summary(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    mine = select(func.count()).select_from(CallLog).where(CallLog.user_id == current_user.id)
    return AccountSummary(
        checks_today=db.scalar(mine.where(CallLog.created_at >= local_midnight_utc(local_today()))) or 0,
        checks_total=db.scalar(mine) or 0,
        risky_found=db.scalar(mine.where(CallLog.risk_score >= 50)) or 0,
        reports_sent=db.scalar(select(func.count()).select_from(Report).where(Report.reported_by == current_user.id)) or 0,
        emergency_contacts=db.scalar(
            select(func.count()).select_from(EmergencyContact).where(EmergencyContact.user_id == current_user.id)) or 0,
    )


@router.get("/ai/status")
async def ai_status():
    return await ai_client.status()


# ======================= Contact =======================

@router.post("/contact", status_code=status.HTTP_201_CREATED)
def submit_contact(payload: ContactRequest, request: Request, db: Session = Depends(get_db)):
    ip = (request.client.host if request.client else None) or "unknown"
    if contact_limiter.is_blocked(ip):
        raise TooManyRequestsError("ส่งข้อความบ่อยเกินไป กรุณาลองใหม่ภายหลัง")
    contact_limiter.hit(ip)
    db.add(ContactMessage(name=payload.name, email=str(payload.email), topic=payload.topic, message=payload.message))
    db.commit()
    return {"success": True, "message": "ได้รับข้อความแล้ว ทีมงานจะตอบกลับทางอีเมลภายใน 1-2 วันทำการ"}


@router.get("/admin/contact-messages", response_model=PaginatedContactMessages)
def list_contact_messages(
    status_filter: ContactStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    query = select(ContactMessage)
    if status_filter is not None:
        query = query.where(ContactMessage.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = db.scalars(
        query.order_by(ContactMessage.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedContactMessages(total=total, page=page, page_size=page_size, items=items)


@router.put("/admin/contact-messages/{message_id}", response_model=ContactMessageOut)
def update_contact_message(
    message_id: uuid.UUID,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    msg = db.get(ContactMessage, message_id)
    if msg is None:
        raise NotFoundError("ไม่พบข้อความนี้")
    msg.status = payload.status
    msg.handled_at = _now() if payload.status == ContactStatus.handled else None
    db.commit()
    db.refresh(msg)
    return msg


@router.get("/admin/overview", response_model=AdminOverview)
def admin_overview(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    now = _now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    paid = select(Payment).where(Payment.status == PaymentStatus.paid, Payment.paid_at >= month_start).subquery()
    return AdminOverview(
        members=db.scalar(select(func.count()).select_from(User).where(User.role == UserRole.member)) or 0,
        premium_members=db.scalar(select(func.count()).select_from(User).where(
            User.role == UserRole.member, User.premium_until > now)) or 0,
        revenue_this_month_baht=db.scalar(select(func.coalesce(func.sum(paid.c.amount_baht), 0))) or 0,
        paid_this_month=db.scalar(select(func.count()).select_from(paid)) or 0,
        new_contact_messages=db.scalar(select(func.count()).select_from(ContactMessage).where(
            ContactMessage.status == ContactStatus.new)) or 0,
        checks_today=db.scalar(select(func.count()).select_from(CallLog).where(
            CallLog.created_at >= local_midnight_utc(local_today()))) or 0,
        blacklist_numbers=db.scalar(select(func.count()).select_from(BlacklistNumber)) or 0,
    )
