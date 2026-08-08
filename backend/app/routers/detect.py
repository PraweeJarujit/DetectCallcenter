"""
Router: Detect Callcenter System
/detect/number, /detect/audio, /report, /blacklist

หมายเหตุ: /detect/audio เป็น "จุดเชื่อมต่อ" (integration point) ที่เตรียมไว้ให้ forward
ไฟล์เสียงไปยังบริการ/โมเดล AI จริงในโฟลเดอร์ voiceguard-ai (ตั้งค่า URL ผ่าน
VOICEGUARD_AI_URL ใน .env) ถ้ายังไม่ได้ deploy บริการนั้น endpoint จะ fallback เป็น
ผลจำลอง (mock) เพื่อไม่ให้ frontend ที่เรียกใช้งาน endpoint นี้พัง
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.blacklist_number import BlacklistNumber, NumberStatus
from app.models.report import Report
from app.models.user import User
from app.schemas.detect import (
    AudioAnalysisResponse,
    BlacklistOut,
    NumberCheckRequest,
    NumberCheckResponse,
    PaginatedBlacklist,
    ReportOut,
    ReportRequest,
    ReportResponse,
)

router = APIRouter(tags=["detect"])


def _status_from_score(score: int) -> NumberStatus:
    if score >= 80:
        return NumberStatus.high_risk
    if score >= 50:
        return NumberStatus.suspect
    return NumberStatus.safe


@router.post("/detect/number", response_model=NumberCheckResponse)
def detect_number(payload: NumberCheckRequest, db: Session = Depends(get_db)):
    record = db.query(BlacklistNumber).filter(BlacklistNumber.phone_number == payload.phone_number).first()
    if record is None:
        # ยังไม่เคยมีข้อมูล ถือว่าปลอดภัยจนกว่าจะมีการ report หรือระบบ AI วิเคราะห์เพิ่มเติม
        return NumberCheckResponse(
            phone_number=payload.phone_number,
            status=NumberStatus.safe,
            risk_score=0,
            report_count=0,
            is_blacklisted=False,
        )

    return NumberCheckResponse(
        phone_number=record.phone_number,
        status=record.status,
        risk_score=record.risk_score,
        report_count=record.report_count,
        is_blacklisted=record.status in (NumberStatus.suspect, NumberStatus.high_risk),
    )


@router.post("/detect/audio", response_model=AudioAnalysisResponse)
async def detect_audio(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
):
    audio_bytes = await file.read()

    # พยายาม forward ไปยังบริการ AI จริงก่อน (โฟลเดอร์ voiceguard-ai)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.VOICEGUARD_AI_URL}/analyze",
                files={"file": (file.filename, audio_bytes, file.content_type)},
            )
            resp.raise_for_status()
            result = resp.json()
            return AudioAnalysisResponse(
                filename=file.filename,
                risk_score=result.get("risk_score", 0),
                is_synthetic_voice=result.get("is_synthetic_voice", False),
                detail=result.get("detail", {}),
            )
    except (httpx.HTTPError, ValueError):
        # บริการ AI จริงยังไม่พร้อมใช้งาน -> คืนผลจำลองเพื่อให้ flow การ integrate ฝั่ง frontend ทำต่อได้
        return AudioAnalysisResponse(
            filename=file.filename,
            risk_score=87,
            is_synthetic_voice=True,
            detail={
                "note": "mock result: บริการ voiceguard-ai ยังไม่พร้อมใช้งาน",
                "pitch_pattern_anomaly": 92,
                "synthetic_artifact_detected": 85,
            },
        )


@router.post("/report", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_report(
    payload: ReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = Report(
        phone_number=payload.phone_number,
        reported_by=current_user.id,
        risk_score=payload.risk_score,
        note=payload.note,
    )
    db.add(report)

    record = db.query(BlacklistNumber).filter(BlacklistNumber.phone_number == payload.phone_number).first()
    if record is None:
        record = BlacklistNumber(
            phone_number=payload.phone_number,
            risk_score=payload.risk_score,
            report_count=1,
            status=_status_from_score(payload.risk_score),
        )
    else:
        record.report_count += 1
        record.risk_score = max(record.risk_score, payload.risk_score)
        record.status = _status_from_score(record.risk_score)
    db.add(record)

    db.commit()
    db.refresh(report)

    return ReportResponse(
        success=True,
        message=f"ส่งรายงานเบอร์ {payload.phone_number} สำเร็จ",
        report=report,
    )


@router.get("/blacklist", response_model=PaginatedBlacklist)
def get_blacklist(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    status_filter: NumberStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    query = db.query(BlacklistNumber)
    if status_filter is not None:
        query = query.filter(BlacklistNumber.status == status_filter)
    query = query.order_by(BlacklistNumber.risk_score.desc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedBlacklist(total=total, page=page, page_size=page_size, items=items)
