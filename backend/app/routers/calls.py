"""
Router: Calls / Dashboard
/calls (POST), /calls/logs, /calls/stats, /calls/trend, /calls/demo-analysis

ทุก query ในไฟล์นี้ออกแบบให้ "ใช้ index ได้" (ดู db-indexing/README.md):
  - กรองเวลาเป็นช่วง  created_at >= :start  (ไม่ครอบ column ด้วย function ใน WHERE)
  - ORDER BY ตรงกับลำดับ column ใน index -> ไม่ต้อง Sort
  - เงื่อนไข risk_score >= 80 ตรงกับ predicate ของ partial index IDX-7
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, literal_column, select, tuple_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.dependencies import get_current_user, get_current_user_optional
from app.models.blacklist_number import HIGH_RISK_THRESHOLD, status_from_score
from app.models.call_log import CallLog
from app.models.user import User
from app.schemas.calls import (
    CallCreate,
    CallLogOut,
    CallStats,
    DemoAnalysis,
    PaginatedCallLogs,
    TrendPoint,
)

router = APIRouter(prefix="/calls", tags=["calls"])

THAI_WEEKDAYS = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]
TREND_DAYS = 7


def _tz() -> ZoneInfo:
    return ZoneInfo(settings.APP_TIMEZONE)


def local_today() -> date:
    return datetime.now(_tz()).date()


def local_midnight_utc(d: date) -> datetime:
    """เที่ยงคืนของวัน d ตามเวลาไทย แปลงเป็น UTC เพื่อใช้เป็นขอบล่างของช่วงเวลา"""
    return datetime.combine(d, time.min, tzinfo=_tz()).astimezone(timezone.utc)


def _local_date_expr(db: Session):
    """
    แปลง created_at -> วันที่ตามเวลาไทย (ใช้ใน SELECT/GROUP BY เท่านั้น — ไม่ใช้ใน WHERE)
    Postgres: date(timezone('Asia/Bangkok', created_at))  |  SQLite (ตอนรัน test): date(created_at, '+7 hours')
    """
    if db.get_bind().dialect.name == "postgresql":
        return func.date(func.timezone(settings.APP_TIMEZONE, CallLog.created_at))
    offset = datetime.now(_tz()).utcoffset() or timedelta(0)
    hours = int(offset.total_seconds() // 3600)
    return func.date(CallLog.created_at, f"{hours:+d} hours")


@router.post("", response_model=CallLogOut, status_code=status.HTTP_201_CREATED)
def create_call_log(
    payload: CallCreate,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    log = CallLog(
        phone_number=payload.phone_number,
        user_id=current_user.id if current_user else None,
        risk_score=payload.risk_score,
        status=status_from_score(payload.risk_score),
        is_synthetic_voice=payload.is_synthetic_voice,
        source=payload.source,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/logs", response_model=PaginatedCallLogs)
def list_call_logs(
    limit: int = Query(default=20, ge=1, le=settings.MAX_PAGE_SIZE),
    before_id: int | None = Query(default=None, ge=1, description="cursor: id ของแถวสุดท้ายจากหน้าก่อน"),
    mine: bool = Query(default=False, description="เฉพาะที่ตัวเองตรวจ"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Keyset pagination (แทน OFFSET): หน้าถัดไปใช้ WHERE (created_at, id) < (cursor)
    ทำให้หน้าที่ 1,000 เร็วเท่าหน้าแรก — OFFSET 20000 ต้องอ่านแล้วทิ้ง 20,000 แถวทุกครั้ง
    และไม่ COUNT(*) ทั้งตาราง (total = None) เพราะ call_logs โตเป็นล้านแถว
    """
    query = select(CallLog)
    if mine:
        query = query.where(CallLog.user_id == current_user.id)  # ใช้ IDX-8
    if before_id is not None:
        cursor = db.execute(
            select(CallLog.created_at, CallLog.id).where(CallLog.id == before_id)
        ).first()
        if cursor is None:
            raise NotFoundError("ไม่พบ cursor ที่ระบุ")
        query = query.where(tuple_(CallLog.created_at, CallLog.id) < tuple_(cursor.created_at, cursor.id))

    items = db.scalars(
        query.order_by(CallLog.created_at.desc(), CallLog.id.desc()).limit(limit + 1)  # ใช้ IDX-6
    ).all()
    has_more = len(items) > limit
    items = items[:limit]
    return PaginatedCallLogs(
        total=None, items=items, next_before_id=items[-1].id if has_more and items else None,
    )


@router.get("/stats", response_model=CallStats)
def call_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = local_midnight_utc(local_today())
    # ❌ WHERE date(created_at) = current_date  -> ครอบ column ด้วย function = Seq Scan ทั้งตาราง
    # ✅ WHERE created_at >= :start              -> Index (Only) Scan บน IDX-6 / IDX-7
    checked_today = db.scalar(
        select(func.count()).select_from(CallLog).where(CallLog.created_at >= start)
    )
    high_risk_today = db.scalar(
        select(func.count()).select_from(CallLog).where(
            CallLog.created_at >= start,
            # literal_column -> SQL ได้ "risk_score >= 80" ตรงตัว ให้ planner จับคู่กับ partial index ได้แน่นอน
            CallLog.risk_score >= literal_column(str(HIGH_RISK_THRESHOLD)),
        )
    )
    return CallStats(
        checked_today=checked_today or 0,
        high_risk_today=high_risk_today or 0,
        model_accuracy=settings.MODEL_ACCURACY,
        blocked_damage_baht=(high_risk_today or 0) * settings.AVG_DAMAGE_PER_CASE_BAHT,
    )


@router.get("/trend", response_model=list[TrendPoint])
def call_trend(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    today = local_today()
    first_day = today - timedelta(days=TREND_DAYS - 1)
    day_expr = _local_date_expr(db).label("d")
    rows = db.execute(
        select(day_expr, func.count().label("n"))
        .where(
            CallLog.created_at >= local_midnight_utc(first_day),
            CallLog.risk_score >= literal_column(str(HIGH_RISK_THRESHOLD)),
        )
        .group_by(day_expr)
    ).all()
    counts = {(r.d if isinstance(r.d, date) else date.fromisoformat(r.d)): r.n for r in rows}

    points = []
    for i in range(TREND_DAYS):
        d = first_day + timedelta(days=i)
        points.append(TrendPoint(date=d, day=THAI_WEEKDAYS[d.weekday()], risky_calls=counts.get(d, 0)))
    return points


@router.get("/demo-analysis", response_model=DemoAnalysis)
def demo_analysis():
    """ผลวิเคราะห์ตัวอย่างสำหรับหน้า Call Demo (ไม่ต้อง login)"""
    return DemoAnalysis(
        risk_score=87,
        breakdown=[
            {"label": "ความผิดปกติของ pitch pattern", "value": 92},
            {"label": "พบ artifact จากการสังเคราะห์เสียง", "value": 85},
            {"label": "จังหวะการหยุดพูดผิดธรรมชาติ", "value": 78},
            {"label": "ความสอดคล้องของสเปกตรัมเสียง", "value": 81},
        ],
    )
