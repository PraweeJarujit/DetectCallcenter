from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.validators import ThaiPhone
from app.models.blacklist_number import NumberStatus
from app.models.call_log import CallSource


class CallCreate(BaseModel):
    """บันทึกผลการตรวจสายจากหน้า Call Demo / client อื่น"""
    phone_number: ThaiPhone
    risk_score: int = Field(ge=0, le=100)
    is_synthetic_voice: bool = False
    source: CallSource = CallSource.demo


class CallLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone_number: str | None
    risk_score: int
    status: NumberStatus
    status_label: str
    is_synthetic_voice: bool
    source: CallSource
    created_at: datetime


class PaginatedCallLogs(BaseModel):
    total: int | None  # None เมื่อใช้ keyset pagination (ไม่ COUNT ทั้งตาราง)
    items: list[CallLogOut]
    next_before_id: int | None = None


class CallStats(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # อนุญาตชื่อ field ขึ้นต้นด้วย model_

    checked_today: int
    high_risk_today: int
    model_accuracy: float
    blocked_damage_baht: int


class TrendPoint(BaseModel):
    date: date
    day: str            # ป้ายชื่อวันภาษาไทยแบบย่อ เช่น "จ."
    risky_calls: int


class BreakdownItem(BaseModel):
    label: str
    value: int


class DemoAnalysis(BaseModel):
    risk_score: int
    breakdown: list[BreakdownItem]
