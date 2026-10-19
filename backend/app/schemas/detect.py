import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.validators import ThaiPhone, strip_text
from app.models.blacklist_number import NumberStatus


class NumberCheckRequest(BaseModel):
    phone_number: ThaiPhone = Field(examples=["081-234-5678"])


class NumberCheckResponse(BaseModel):
    phone_number: str
    status: NumberStatus
    status_label: str
    risk_score: int
    report_count: int
    is_blacklisted: bool
    # จำนวนครั้งที่ยังตรวจฟรีได้วันนี้ (None = Premium ไม่จำกัด)
    remaining_today: int | None = None


class AudioAnalysisResponse(BaseModel):
    """ผลจาก /detect/audio — คำนวณโดยโมเดลใน ai-service (ดู ai-service/models/voice_metrics.json)"""
    filename: str
    risk_score: int = Field(ge=0, le=100)
    is_synthetic_voice: bool
    is_mock: bool = False
    detail: dict
    alerted_contacts: list[str] = Field(default_factory=list)


class TextCheckRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000, examples=["บัญชีของคุณถูกระงับ กรุณายืนยันตัวตนที่ลิงก์นี้"])
    phone_number: ThaiPhone | None = None

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("กรุณาใส่ข้อความที่ต้องการตรวจ")
        return v


class TextSignal(BaseModel):
    code: str
    label: str
    match: str


class TextAnalysisResponse(BaseModel):
    risk_score: int = Field(ge=0, le=100)
    scam_probability: float
    level: str
    level_label: str
    signals: list[TextSignal]
    is_mock: bool = False
    alerted_contacts: list[str] = Field(default_factory=list)


# ---------- Category (Many-to-Many กับ Report) ----------

class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str


# ---------- Report ----------

class ReportRequest(BaseModel):
    phone_number: ThaiPhone
    risk_score: int = Field(default=0, ge=0, le=100)
    note: str | None = Field(default=None, max_length=1000)
    category_codes: list[str] = Field(default_factory=list, max_length=5,
                                      examples=[["impersonate_police", "voice_clone"]])

    @field_validator("note")
    @classmethod
    def _strip_note(cls, v: str | None) -> str | None:
        return strip_text(v)

    @field_validator("category_codes")
    @classmethod
    def _dedupe_codes(cls, v: list[str]) -> list[str]:
        # ตัดค่าซ้ำแต่คงลำดับเดิม
        return list(dict.fromkeys(c.strip() for c in v if c.strip()))


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    risk_score: int
    note: str | None
    reporter_username: str | None
    categories: list[CategoryOut]
    created_at: datetime


class ReportResponse(BaseModel):
    success: bool
    message: str
    report: ReportOut


class PaginatedReports(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ReportOut]


# ---------- Blacklist ----------

class BlacklistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    phone_number: str
    status: NumberStatus
    status_label: str
    risk_score: int
    report_count: int
    first_reported_at: datetime
    last_reported_at: datetime


class BlacklistDetail(BlacklistOut):
    reports: list[ReportOut]


class BlacklistCreate(BaseModel):
    """admin เพิ่มเบอร์เข้า blacklist โดยตรง (เช่น ได้รับแจ้งจากหน่วยงานอื่น)"""
    phone_number: ThaiPhone
    risk_score: int = Field(ge=0, le=100)
    status: NumberStatus | None = None  # ไม่ส่งมา = คำนวณจาก risk_score


class BlacklistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_score: int | None = Field(default=None, ge=0, le=100)
    status: NumberStatus | None = None


class PaginatedBlacklist(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[BlacklistOut]
