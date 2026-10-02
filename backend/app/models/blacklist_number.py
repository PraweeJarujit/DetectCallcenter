import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow

if TYPE_CHECKING:
    from app.models.report import Report


# เกณฑ์ risk score -> สถานะ (ค่าคงที่ ไม่ให้ตั้งผ่าน env เพราะ partial index IDX-7
# ใน call_logs ผูกกับเลข 80 ไว้ — ถ้าเปลี่ยนต้องสร้าง migration แก้ index ด้วย)
HIGH_RISK_THRESHOLD = 80
SUSPECT_THRESHOLD = 50


def status_from_score(score: int) -> "NumberStatus":
    if score >= HIGH_RISK_THRESHOLD:
        return NumberStatus.high_risk
    if score >= SUSPECT_THRESHOLD:
        return NumberStatus.suspect
    return NumberStatus.safe


class NumberStatus(str, enum.Enum):
    safe = "safe"
    suspect = "suspect"
    high_risk = "high_risk"


STATUS_LABELS = {
    NumberStatus.safe: "ปลอดภัย",
    NumberStatus.suspect: "น่าสงสัย",
    NumberStatus.high_risk: "เสี่ยงสูง",
}


class BlacklistNumber(Base):
    """
    ข้อมูลสรุป (1 แถวต่อ 1 เบอร์) ของเบอร์ที่เคยถูก report หรือระบบตรวจพบว่ามีความเสี่ยง
    รายละเอียดการแจ้งแต่ละครั้งอยู่ในตาราง reports (One-to-Many: 1 เบอร์ -> หลาย report)
    report_count / risk_score เป็นค่าสรุปที่อัปเดตทุกครั้งที่มี report ใหม่ (denormalized
    โดยตั้งใจ เพื่อให้ /detect/number ตอบได้ใน 1 index lookup ไม่ต้อง COUNT ทุกครั้ง)
    """
    __tablename__ = "blacklist_numbers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[NumberStatus] = mapped_column(
        Enum(NumberStatus, native_enum=False, length=10, validate_strings=True),
        default=NumberStatus.suspect, nullable=False,
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # 0-100
    report_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    first_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    last_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )

    reports: Mapped[list["Report"]] = relationship(
        back_populates="blacklist_number", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Report.created_at.desc()",
    )

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, str(self.status))


# ---------- INDEXES (ดูเหตุผลเต็มใน db-indexing/README.md) ----------
# ประกาศหลัง class เพื่ออ้าง column จริงได้ (เช่น .desc()) — Index ที่ผูก column ของตารางจะถูกเพิ่มเข้า table อัตโนมัติ

# [IDX-1] unique + varchar_pattern_ops: index เดียวรองรับ 2 งาน
#   - WHERE phone_number = '0812345678'      (/detect/number, /report upsert)
#   - WHERE phone_number LIKE '0812%'         (ช่องค้นหาในหน้า Blacklist)
#   btree ปกติบน collation en_US ใช้กับ LIKE 'prefix%' ไม่ได้ (เหมือน lab 04 ข้อ 4.3)
Index(
    "uq_blacklist_numbers_phone", BlacklistNumber.phone_number, unique=True,
    postgresql_ops={"phone_number": "varchar_pattern_ops"},
)
# [IDX-2] composite (status, risk_score DESC, id): /blacklist?status=high_risk ORDER BY risk_score DESC LIMIT 20
#   -> อ่านตามลำดับ index ได้เลย ไม่ต้อง Sort ทั้งตาราง
#   status อย่างเดียวมีแค่ 3 ค่า (cardinality ต่ำ, lab 04 ข้อ 4.4) จึงต้องเป็น composite
Index(
    "ix_blacklist_numbers_status_risk",
    BlacklistNumber.status, BlacklistNumber.risk_score.desc(), BlacklistNumber.id,
)
# [IDX-3] (risk_score DESC, id): หน้า Blacklist แบบไม่กรอง status
#   ใช้ IDX-2 ไม่ได้เพราะข้าม column ซ้ายสุด (leftmost rule, lab 05)
Index("ix_blacklist_numbers_risk", BlacklistNumber.risk_score.desc(), BlacklistNumber.id)
