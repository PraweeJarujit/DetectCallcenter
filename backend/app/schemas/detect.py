import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.blacklist_number import NumberStatus


class NumberCheckRequest(BaseModel):
    phone_number: str = Field(min_length=9, max_length=20, examples=["0812345678"])


class NumberCheckResponse(BaseModel):
    phone_number: str
    status: NumberStatus
    risk_score: int
    report_count: int
    is_blacklisted: bool


class AudioAnalysisResponse(BaseModel):
    """
    ผลตอบกลับจาก /detect/audio
    หมายเหตุ: endpoint นี้เป็นจุดเชื่อมต่อ (integration point) ไปยังโมเดล/บริการจริง
    ในโฟลเดอร์ voiceguard-ai — ปัจจุบัน forward ไฟล์ไปหรือ mock ผลถ้ายังเชื่อมต่อไม่ได้
    """
    filename: str
    risk_score: int
    is_synthetic_voice: bool
    detail: dict


class ReportRequest(BaseModel):
    phone_number: str = Field(min_length=9, max_length=20)
    risk_score: int = Field(default=0, ge=0, le=100)
    note: str | None = None


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    risk_score: int
    note: str | None
    created_at: datetime


class ReportResponse(BaseModel):
    success: bool
    message: str
    report: ReportOut


class BlacklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    phone_number: str
    status: NumberStatus
    risk_score: int
    report_count: int
    last_reported_at: datetime


class PaginatedBlacklist(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BlacklistOut]
