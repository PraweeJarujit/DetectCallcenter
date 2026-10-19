"""
Router: ตรวจระหว่างสาย (เรียลไทม์)

หน้าเว็บ (pages/live.html) อัดเสียงจากไมค์ / เสียงระบบ / สายตัวอย่าง แล้วส่งมาทีละช่วง:
  POST /live/chunk    เสียงช่วงละ ~4 วินาที (WAV) -> โมเดลเสียง ตอบความน่าจะเป็นเสียงสังเคราะห์
  POST /live/text     คำพูดที่ถอดได้ระหว่างสาย -> โมเดลข้อความ (Premium) ไม่บันทึกประวัติทุกครั้งที่ส่ง
  POST /live/summary  จบสาย -> บันทึกผลรวม 1 แถวลงประวัติ + แจ้งผู้ติดต่อฉุกเฉินถ้าเสี่ยงสูง (Premium)
  GET  /live/quota    สิทธิ์ที่เหลือของวันนี้

สิทธิ์: Premium ไม่จำกัด / คนอื่นทดลองฟรี LIVE_FREE_CHUNKS_PER_DAY ช่วงต่อวัน (นับตามบัญชี หรือ IP ถ้าไม่ login)
ไม่เก็บไฟล์เสียงหรือคำพูด เก็บเฉพาะผลตรวจตอนจบสาย
"""
from fastapi import APIRouter, Depends, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, PayloadTooLargeError, QuotaExceededError, TooManyRequestsError
from app.core.rate_limit import SlidingWindowLimiter
from app.database import get_db
from app.dependencies import get_current_user_optional, require_premium
from app.models.blacklist_number import status_from_score
from app.models.call_log import CallLog, CallSource
from app.models.user import User
from app.routers.detect import LEVEL_LABELS, _alert_contacts
from app.schemas.detect import TextSignal
from app.core.validators import ThaiPhone
from app.services import ai_client

router = APIRouter(prefix="/live", tags=["live"])

CHUNK_SECONDS = 4
HOP_SECONDS = 2
live_quota = SlidingWindowLimiter(settings.LIVE_FREE_CHUNKS_PER_DAY, 24 * 3600)
summary_limiter = SlidingWindowLimiter(30, 3600)


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


def _quota_key(user: User | None, request: Request) -> str:
    return f"user:{user.id}" if user else f"ip:{_client_ip(request)}"


class LiveQuota(BaseModel):
    premium: bool
    free_chunks_left: int | None = Field(description="ช่วงเสียงที่ตรวจฟรีได้อีกวันนี้ (None = ไม่จำกัด)")
    free_seconds_left: int | None
    chunk_seconds: int = CHUNK_SECONDS
    hop_seconds: int = HOP_SECONDS
    text_analysis: bool = Field(description="วิเคราะห์คำพูดระหว่างสายได้หรือไม่ (Premium)")


class LiveChunkOut(BaseModel):
    synthetic_probability: float
    risk_score: int = Field(ge=0, le=100)
    processing_ms: int | None = None
    free_chunks_left: int | None = None


class LiveTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)


class LiveTextOut(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    level: str
    level_label: str
    signals: list[TextSignal]


class LiveSummaryRequest(BaseModel):
    phone_number: ThaiPhone | None = None
    duration_seconds: int = Field(ge=0, le=6 * 3600)
    voice_risk: int = Field(ge=0, le=100, description="คะแนนเสียงสังเคราะห์สูงสุดระหว่างสาย (ค่าเฉลี่ยเคลื่อนที่)")
    text_risk: int | None = Field(default=None, ge=0, le=100)
    chunks_analyzed: int = Field(ge=0, le=20000)


class LiveSummaryOut(BaseModel):
    risk_score: int
    status: str
    is_synthetic_voice: bool
    alerted_contacts: list[str]


def _remaining(user: User | None, request: Request) -> int | None:
    if user is not None and user.is_premium:
        return None
    return live_quota.remaining(_quota_key(user, request))


@router.get("/quota", response_model=LiveQuota)
def quota(request: Request, current_user: User | None = Depends(get_current_user_optional)):
    left = _remaining(current_user, request)
    premium = left is None
    return LiveQuota(premium=premium, free_chunks_left=left,
                     free_seconds_left=None if premium else left * HOP_SECONDS,
                     text_analysis=premium)


@router.post("/chunk", response_model=LiveChunkOut)
async def analyze_chunk(
    file: UploadFile,
    request: Request,
    current_user: User | None = Depends(get_current_user_optional),
):
    premium = current_user is not None and current_user.is_premium
    key = _quota_key(current_user, request)
    if not premium and live_quota.is_blocked(key):
        raise QuotaExceededError(
            f"ทดลองตรวจระหว่างสายฟรีครบสำหรับวันนี้แล้ว สมัคร Premium {settings.PREMIUM_PRICE_BAHT} บาท/เดือน "
            "เพื่อตรวจได้ไม่จำกัดทุกสาย")
    data = await file.read(settings.LIVE_MAX_CHUNK_BYTES + 1)
    if len(data) > settings.LIVE_MAX_CHUNK_BYTES:
        raise PayloadTooLargeError("ช่วงเสียงยาวเกินไป (ส่งได้ครั้งละไม่เกิน ~8 วินาที)")
    if not data:
        raise BadRequestError("ไม่มีข้อมูลเสียง")

    result = await ai_client.analyze_audio(data, file.filename or "chunk.wav", file.content_type or "audio/wav")
    if not premium:
        live_quota.hit(key)
    detail = result.get("detail", {})
    prob = float(detail.get("synthetic_probability", result.get("risk_score", 0) / 100))
    return LiveChunkOut(
        synthetic_probability=round(prob, 4),
        risk_score=max(0, min(100, int(round(prob * 100)))),
        processing_ms=detail.get("processing_ms"),
        free_chunks_left=None if premium else live_quota.remaining(key),
    )


@router.post("/text", response_model=LiveTextOut)
async def analyze_live_text(payload: LiveTextRequest, current_user: User = Depends(require_premium)):
    data = await ai_client.analyze_text(payload.text.strip()[-3000:])
    level = data.get("level", "low")
    return LiveTextOut(
        risk_score=max(0, min(100, int(data.get("risk_score", 0)))),
        level=level, level_label=LEVEL_LABELS.get(level, level), signals=data.get("signals", []),
    )


@router.post("/summary", response_model=LiveSummaryOut)
def summary(
    payload: LiveSummaryRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    ip = _client_ip(request)
    if current_user is None:
        if summary_limiter.is_blocked(ip):
            raise TooManyRequestsError("บันทึกผลบ่อยเกินไป ลองใหม่ภายหลัง")
        summary_limiter.hit(ip)
    risk = max(payload.voice_risk, payload.text_risk or 0)
    synthetic = payload.voice_risk >= 50 and payload.chunks_analyzed > 0
    log = CallLog(
        phone_number=payload.phone_number, user_id=current_user.id if current_user else None,
        risk_score=risk, status=status_from_score(risk), is_synthetic_voice=synthetic, source=CallSource.live,
    )
    db.add(log)
    db.commit()
    alerted = _alert_contacts(current_user, risk) if current_user is not None and current_user.is_premium else []
    return LiveSummaryOut(risk_score=risk, status=log.status.value, is_synthetic_voice=synthetic,
                          alerted_contacts=alerted)
