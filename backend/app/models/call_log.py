import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow
from app.models.blacklist_number import HIGH_RISK_THRESHOLD, STATUS_LABELS, NumberStatus

if TYPE_CHECKING:
    from app.models.user import User


class CallSource(str, enum.Enum):
    number_check = "number_check"   # ตรวจเบอร์ผ่าน /detect/number
    audio = "audio"                 # วิเคราะห์ไฟล์เสียงผ่าน /detect/audio
    demo = "demo"                   # จากหน้า Call Demo


class CallLog(Base):
    """
    บันทึกทุกครั้งที่ระบบตรวจสอบสาย/เบอร์ — เป็นตารางที่โตเร็วที่สุดในระบบ
    (ข้อมูลของ dashboard: สถิติวันนี้, แนวโน้ม 7 วัน, Call Logs ล่าสุด)

    ใช้ BIGINT identity เป็น PK แทน UUID: ค่าเรียงตามเวลาที่ insert -> index PK แน่นและ
    insert ต่อท้าย B-tree เสมอ (UUID สุ่มทำให้ insert กระจายทั่ว index / page split บ่อย)
    """
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[NumberStatus] = mapped_column(
        Enum(NumberStatus, native_enum=False, length=10, validate_strings=True), nullable=False
    )
    is_synthetic_voice: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[CallSource] = mapped_column(
        Enum(CallSource, native_enum=False, length=15, validate_strings=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    user: Mapped["User | None"] = relationship(back_populates="call_logs")

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, str(self.status))


# ---------- INDEXES ----------
# [IDX-6] (created_at DESC, id DESC): ทุก query ของ dashboard กรองหรือเรียงตามเวลา
#   - สถิติวันนี้:   WHERE created_at >= :เที่ยงคืนวันนี้      (range scan)
#   - Call Logs:     ORDER BY created_at DESC, id DESC LIMIT 20  (อ่าน 20 entry แรกของ index แล้วหยุด)
#   ใส่ id ต่อท้ายเพื่อให้ลำดับไม่กำกวมเมื่อเวลาเท่ากัน และใช้ทำ keyset pagination ได้
#   ** ต้องเขียน WHERE เป็นช่วงเวลา ห้ามเขียน date(created_at) = today (lab 04 ข้อ 4.1)
Index("ix_call_logs_created", CallLog.created_at.desc(), CallLog.id.desc())
# [IDX-7] PARTIAL index เฉพาะสายเสี่ยงสูง (risk_score >= 80 ≈ 20% ของข้อมูล)
#   ใช้กับ "สายเสี่ยงสูงวันนี้" และกราฟแนวโน้ม 7 วัน -> index เล็กกว่า IDX-6 ~5 เท่า
#   และทำ Index Only Scan ได้ (นับจาก index ล้วน ไม่ต้องเปิด table)
Index(
    "ix_call_logs_high_risk_created", CallLog.created_at,
    postgresql_where=CallLog.risk_score >= HIGH_RISK_THRESHOLD,
    sqlite_where=CallLog.risk_score >= HIGH_RISK_THRESHOLD,
)
# [IDX-8] (user_id, created_at DESC, id DESC) WHERE user_id IS NOT NULL: ประวัติการตรวจของผู้ใช้
#   (/calls/logs?mine=true) + รองรับ FK ON DELETE SET NULL
#   ครึ่งหนึ่งของ call_logs มาจากผู้ไม่ login (user_id = NULL) และไม่มี query ไหนค้น NULL
#   -> ทำเป็น partial index ตัดแถว NULL ทิ้ง ขนาดลดลง ~ครึ่ง (วัดจริง 86 MB -> 47 MB ที่ 2 ล้านแถว)
Index(
    "ix_call_logs_user_created", CallLog.user_id, CallLog.created_at.desc(), CallLog.id.desc(),
    postgresql_where=CallLog.user_id.isnot(None),
    sqlite_where=CallLog.user_id.isnot(None),
)
