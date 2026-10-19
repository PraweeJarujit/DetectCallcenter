"""
Router: Detect Callcenter System
/detect/number, /detect/audio, /detect/text, /report, /reports/me, /categories, /blacklist (CRUD)

สิทธิ์การใช้งาน
  - /detect/number : ฟรี 5 ครั้ง/วัน (ไม่ login นับตาม IP, login นับตามบัญชี) / Premium ไม่จำกัด
  - /detect/audio, /detect/text : เฉพาะ Premium — ส่งต่อให้โมเดลจริงใน ai-service (app/services/ai_client.py)
"""
import logging

from fastapi import APIRouter, Depends, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PayloadTooLargeError,
    QuotaExceededError,
)
from app.core.rate_limit import SlidingWindowLimiter
from app.core.validators import validate_phone_prefix, validate_thai_phone
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional, require_admin, require_premium
from app.models.blacklist_number import HIGH_RISK_THRESHOLD, BlacklistNumber, NumberStatus, status_from_score
from app.models.call_log import CallLog, CallSource
from app.models.report import Report
from app.models.scam_category import ScamCategory
from app.models.user import User
from app.routers.calls import local_midnight_utc, local_today
from app.schemas.detect import (
    AudioAnalysisResponse,
    BlacklistCreate,
    BlacklistDetail,
    BlacklistOut,
    BlacklistUpdate,
    CategoryOut,
    NumberCheckRequest,
    NumberCheckResponse,
    PaginatedBlacklist,
    PaginatedReports,
    ReportOut,
    ReportRequest,
    ReportResponse,
    TextAnalysisResponse,
    TextCheckRequest,
)
from app.services import ai_client

router = APIRouter(tags=["detect"])
logger = logging.getLogger("app.detect")

ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/wave", "audio/mpeg", "audio/mp3",
    "audio/ogg", "audio/webm", "audio/mp4", "audio/x-m4a", "audio/aac", "audio/m4a",
    "video/mp4", "application/octet-stream",
}
REPORTS_IN_DETAIL = 50
LEVEL_LABELS = {"high": "น่าจะเป็นมิจฉาชีพ", "medium": "น่าสงสัย ควรระวัง", "low": "ไม่พบสัญญาณอันตราย"}

# ผู้ที่ไม่ได้ login: นับโควตาตรวจเบอร์ฟรีตาม IP (หน้าต่าง 24 ชม.)
anonymous_quota = SlidingWindowLimiter(settings.FREE_DAILY_NUMBER_CHECKS, 24 * 3600)


def _get_blacklist_by_phone(db: Session, phone: str) -> BlacklistNumber | None:
    # ใช้ IDX-1 (unique index บน phone_number) -> Index Scan 1 แถว
    return db.scalar(select(BlacklistNumber).where(BlacklistNumber.phone_number == phone))


def _phone_from_path(phone: str) -> str:
    try:
        return validate_thai_phone(phone)
    except ValueError as e:
        raise BadRequestError(str(e)) from None


def _quota_message() -> str:
    return (f"ตรวจเบอร์ฟรีครบ {settings.FREE_DAILY_NUMBER_CHECKS} ครั้งของวันนี้แล้ว "
            f"สมัคร Premium {settings.PREMIUM_PRICE_BAHT} บาท/เดือน เพื่อตรวจได้ไม่จำกัด")


def number_checks_today(db: Session, user: User) -> int:
    # ใช้ IDX-8 (user_id, created_at DESC) -> นับเฉพาะแถวของผู้ใช้คนนี้ในวันนี้
    return db.scalar(
        select(func.count()).select_from(CallLog).where(
            CallLog.user_id == user.id,
            CallLog.created_at >= local_midnight_utc(local_today()),
            CallLog.source == CallSource.number_check,
        )
    ) or 0


def _alert_contacts(user: User, risk_score: int) -> list[str]:
    """
    แจ้งผู้ติดต่อฉุกเฉินเมื่อพบความเสี่ยงสูง (ถ้าผู้ใช้เปิด auto_notify)
    ตอนนี้ยังไม่ได้ต่อผู้ให้บริการ SMS จริง -> บันทึก log และคืนรายชื่อที่ "จะ" ถูกแจ้ง
    """
    if risk_score < HIGH_RISK_THRESHOLD or not user.auto_notify:
        return []
    names = [c.name for c in user.emergency_contacts]
    if names:
        logger.info("alert (simulated SMS) user=%s contacts=%d score=%d", user.username, len(names), risk_score)
    return names


# ======================= Detect =======================

@router.post("/detect/number", response_model=NumberCheckResponse)
def detect_number(
    payload: NumberCheckRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    remaining: int | None = None
    if current_user is None:
        ip = (request.client.host if request.client else None) or "unknown"
        if anonymous_quota.is_blocked(ip):
            raise QuotaExceededError(_quota_message() + " (หรือสมัครสมาชิกฟรีเพื่อดูประวัติการตรวจ)")
        anonymous_quota.hit(ip)
        remaining = anonymous_quota.remaining(ip)
    elif not current_user.is_premium:
        used = number_checks_today(db, current_user)
        if used >= settings.FREE_DAILY_NUMBER_CHECKS:
            raise QuotaExceededError(_quota_message())
        remaining = settings.FREE_DAILY_NUMBER_CHECKS - used - 1

    record = _get_blacklist_by_phone(db, payload.phone_number)
    if record is None:
        # ยังไม่เคยมีข้อมูล ถือว่าปลอดภัยจนกว่าจะมีการ report หรือระบบ AI วิเคราะห์เพิ่มเติม
        result = NumberCheckResponse(
            phone_number=payload.phone_number, status=NumberStatus.safe, status_label="ไม่พบในรายชื่อเบอร์อันตราย",
            risk_score=0, report_count=0, is_blacklisted=False,
        )
    else:
        result = NumberCheckResponse(
            phone_number=record.phone_number,
            status=record.status,
            status_label=record.status_label,
            risk_score=record.risk_score,
            report_count=record.report_count,
            is_blacklisted=record.status in (NumberStatus.suspect, NumberStatus.high_risk),
        )
    result.remaining_today = remaining

    # บันทึกทุกการตรวจลง call_logs เพื่อใช้ทำสถิติ / ประวัติของผู้ใช้
    db.add(CallLog(
        phone_number=result.phone_number, user_id=current_user.id if current_user else None,
        risk_score=result.risk_score, status=result.status, source=CallSource.number_check,
    ))
    db.commit()
    return result


@router.post("/detect/audio", response_model=AudioAnalysisResponse)
async def detect_audio(
    file: UploadFile,
    phone_number: str | None = Query(default=None, description="เบอร์ที่โทรเข้า (ถ้ามี) ใช้บันทึกประวัติ"),
    current_user: User = Depends(require_premium),
    db: Session = Depends(get_db),
):
    if file.content_type and file.content_type not in ALLOWED_AUDIO_TYPES:
        raise BadRequestError(f"ไม่รองรับไฟล์ประเภท {file.content_type} (รองรับ wav, mp3, m4a, ogg, webm)")
    audio_bytes = await file.read(settings.MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > settings.MAX_AUDIO_BYTES:
        raise PayloadTooLargeError(f"ไฟล์เสียงต้องมีขนาดไม่เกิน {settings.MAX_AUDIO_BYTES // (1024 * 1024)} MB")
    if not audio_bytes:
        raise BadRequestError("ไฟล์เสียงว่างเปล่า")
    phone = _phone_from_path(phone_number) if phone_number else None

    filename = file.filename or "audio"
    data = await ai_client.analyze_audio(audio_bytes, filename, file.content_type)
    result = AudioAnalysisResponse(
        filename=filename,
        risk_score=max(0, min(100, int(data.get("risk_score", 0)))),
        is_synthetic_voice=bool(data.get("is_synthetic_voice", False)),
        is_mock=bool(data.get("is_mock", False)),
        detail=data.get("detail", {}),
    )
    result.alerted_contacts = _alert_contacts(current_user, result.risk_score)
    db.add(CallLog(
        phone_number=phone, user_id=current_user.id, risk_score=result.risk_score,
        status=status_from_score(result.risk_score), is_synthetic_voice=result.is_synthetic_voice,
        source=CallSource.audio,
    ))
    db.commit()
    return result


@router.post("/detect/text", response_model=TextAnalysisResponse)
async def detect_text(
    payload: TextCheckRequest,
    current_user: User = Depends(require_premium),
    db: Session = Depends(get_db),
):
    data = await ai_client.analyze_text(payload.text)
    level = data.get("level", "low")
    result = TextAnalysisResponse(
        risk_score=max(0, min(100, int(data.get("risk_score", 0)))),
        scam_probability=float(data.get("scam_probability", 0.0)),
        level=level,
        level_label=LEVEL_LABELS.get(level, level),
        signals=data.get("signals", []),
        is_mock=bool(data.get("is_mock", False)),
    )
    result.alerted_contacts = _alert_contacts(current_user, result.risk_score)
    db.add(CallLog(
        phone_number=payload.phone_number, user_id=current_user.id, risk_score=result.risk_score,
        status=status_from_score(result.risk_score), source=CallSource.text,
    ))
    db.commit()
    return result


# ======================= Categories =======================

@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(ScamCategory).order_by(ScamCategory.id)).all()


# ======================= Report =======================

def _upsert_blacklist(db: Session, phone: str, risk_score: int) -> BlacklistNumber:
    record = _get_blacklist_by_phone(db, phone)
    if record is None:
        record = BlacklistNumber(
            phone_number=phone, risk_score=risk_score, report_count=1,
            status=status_from_score(risk_score),
        )
        try:
            with db.begin_nested():  # SAVEPOINT: ถ้ามีอีก request insert เบอร์เดียวกันไปก่อน จะไม่พังทั้ง transaction
                db.add(record)
            return record
        except IntegrityError:
            record = _get_blacklist_by_phone(db, phone)
            if record is None:  # pragma: no cover - ไม่ควรเกิด
                raise
    # มีอยู่แล้ว: เพิ่มจำนวนครั้งแบบ atomic ใน SQL (report_count = report_count + 1) กัน lost update
    record.report_count = BlacklistNumber.report_count + 1
    record.risk_score = max(record.risk_score, risk_score)
    record.status = status_from_score(record.risk_score)
    return record


@router.post("/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    categories: list[ScamCategory] = []
    if payload.category_codes:
        categories = list(db.scalars(
            select(ScamCategory).where(ScamCategory.code.in_(payload.category_codes))
        ).all())
        unknown = set(payload.category_codes) - {c.code for c in categories}
        if unknown:
            raise BadRequestError("ไม่รู้จักประเภทการหลอกลวง: " + ", ".join(sorted(unknown)),
                                  details={"unknown_codes": sorted(unknown)})

    record = _upsert_blacklist(db, payload.phone_number, payload.risk_score)
    report = Report(
        blacklist_number=record,
        reporter=current_user,
        risk_score=payload.risk_score,
        note=payload.note,
        categories=categories,
    )
    db.add(report)
    db.commit()
    db.refresh(record)
    logger.info("report submitted phone=%s by=%s", payload.phone_number, current_user.username)

    return ReportResponse(
        success=True,
        message=f"ส่งรายงานเบอร์ {payload.phone_number} สำเร็จ",
        report=ReportOut.model_validate(report),
    )


@router.get("/reports/me", response_model=PaginatedReports)
def my_reports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = select(Report).where(Report.reported_by == current_user.id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    # ใช้ IDX-5 (reported_by, created_at DESC) + eager load กัน N+1:
    #   joinedload  -> blacklist_number (many-to-one: JOIN ไปในคำสั่งเดียว)
    #   selectinload-> categories (many-to-many: 1 query เพิ่ม "WHERE report_id IN (...)")
    items = db.scalars(
        base.options(joinedload(Report.blacklist_number), selectinload(Report.categories))
        .order_by(Report.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedReports(total=total, page=page, page_size=page_size, items=items)


# ======================= Blacklist =======================

@router.get("/blacklist", response_model=PaginatedBlacklist)
def get_blacklist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status_filter: NumberStatus | None = Query(default=None, alias="status"),
    q: str | None = Query(default=None, max_length=20, description="ค้นหาเบอร์ที่ขึ้นต้นด้วย (prefix)"),
    db: Session = Depends(get_db),
):
    query = select(BlacklistNumber)
    if status_filter is not None:
        query = query.where(BlacklistNumber.status == status_filter)
    if q:
        try:
            prefix = validate_phone_prefix(q)
        except ValueError as e:
            raise BadRequestError(str(e)) from None
        # LIKE 'prefix%' (ขึ้นต้นด้วยคำ) ใช้ IDX-1 ได้ ต่างจาก LIKE '%xxx' ที่ต้อง Seq Scan (lab 04 ข้อ 4.3)
        query = query.where(BlacklistNumber.phone_number.like(prefix + "%"))

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    # ORDER BY ตรงกับลำดับใน IDX-2/IDX-3 (risk_score DESC, id) -> ไม่ต้อง Sort, LIMIT หยุดอ่านได้ทันที
    items = db.scalars(
        query.order_by(BlacklistNumber.risk_score.desc(), BlacklistNumber.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedBlacklist(total=total, page=page, page_size=page_size, items=items)


@router.get("/blacklist/{phone}", response_model=BlacklistDetail)
def get_blacklist_detail(
    phone: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _get_blacklist_by_phone(db, _phone_from_path(phone))
    if record is None:
        raise NotFoundError("ไม่พบเบอร์นี้ในระบบ blacklist")
    # ดึง report ล่าสุด 50 รายการด้วย IDX-4 พร้อม eager load ผู้แจ้ง + หมวดหมู่ (รวม 2 query ไม่ว่ากี่ report)
    reports = db.scalars(
        select(Report)
        .where(Report.blacklist_number_id == record.id)
        .options(joinedload(Report.reporter), selectinload(Report.categories))
        .order_by(Report.created_at.desc())
        .limit(REPORTS_IN_DETAIL)
    ).all()
    data = BlacklistOut.model_validate(record).model_dump()
    data["reports"] = [ReportOut.model_validate(r) for r in reports]
    return BlacklistDetail(**data)


@router.post("/blacklist", response_model=BlacklistOut, status_code=status.HTTP_201_CREATED)
def create_blacklist(
    payload: BlacklistCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    if _get_blacklist_by_phone(db, payload.phone_number):
        raise ConflictError("เบอร์นี้อยู่ใน blacklist แล้ว ใช้ PUT เพื่อแก้ไขแทน")
    record = BlacklistNumber(
        phone_number=payload.phone_number,
        risk_score=payload.risk_score,
        status=payload.status or status_from_score(payload.risk_score),
        report_count=0,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("เบอร์นี้อยู่ใน blacklist แล้ว") from None
    db.refresh(record)
    return record


@router.put("/blacklist/{phone}", response_model=BlacklistOut)
def update_blacklist(
    phone: str,
    payload: BlacklistUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    record = _get_blacklist_by_phone(db, _phone_from_path(phone))
    if record is None:
        raise NotFoundError("ไม่พบเบอร์นี้ในระบบ blacklist")
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise BadRequestError("ไม่มีข้อมูลที่ต้องแก้ไข")
    if "risk_score" in data:
        record.risk_score = data["risk_score"]
        if "status" not in data:
            record.status = status_from_score(record.risk_score)
    if "status" in data:
        record.status = data["status"]
    db.commit()
    db.refresh(record)
    return record


@router.delete("/blacklist/{phone}")
def delete_blacklist(
    phone: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    record = _get_blacklist_by_phone(db, _phone_from_path(phone))
    if record is None:
        raise NotFoundError("ไม่พบเบอร์นี้ในระบบ blacklist")
    phone_number = record.phone_number
    db.delete(record)  # report ของเบอร์นี้ถูกลบตาม (ON DELETE CASCADE — เร็วเพราะมี IDX-4)
    db.commit()
    return {"success": True, "message": f"ลบเบอร์ {phone_number} ออกจาก blacklist แล้ว"}
