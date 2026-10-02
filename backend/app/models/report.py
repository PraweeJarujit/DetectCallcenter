import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow

if TYPE_CHECKING:
    from app.models.blacklist_number import BlacklistNumber
    from app.models.scam_category import ScamCategory
    from app.models.user import User


# ---------- Many-to-Many: Report <-> ScamCategory ----------
# 1 report ระบุได้หลายรูปแบบการหลอก (เช่น แอบอ้างตำรวจ + ใช้เสียงสังเคราะห์)
# 1 รูปแบบการหลอก ถูกใช้ในหลาย report
report_categories = Table(
    "report_categories",
    Base.metadata,
    Column("report_id", Uuid, ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", Integer, ForeignKey("scam_categories.id", ondelete="CASCADE"), primary_key=True),
    # PK (report_id, category_id) ใช้ค้น "หมวดของ report นี้" ได้แล้ว แต่ค้นกลับ
    # "report ทั้งหมดของหมวดนี้" ต้องมี index ที่ขึ้นต้นด้วย category_id (leftmost rule)
    Index("ix_report_categories_category", "category_id"),
)


class Report(Base):
    """
    การแจ้งเบาะแสแต่ละครั้ง (1 แถวต่อ 1 การแจ้ง)

    ความสัมพันธ์:
      - BlacklistNumber 1 ── N Report   (blacklist_number_id, ลบเบอร์ -> ลบ report ตาม)
      - User            1 ── N Report   (reported_by, ลบ user -> report ยังอยู่แต่ไม่ระบุผู้แจ้ง)
      - Report          N ── N ScamCategory  (ผ่านตาราง report_categories)

    Normalization: เดิมเก็บ phone_number ซ้ำในทุก report — ตอนนี้อ้างผ่าน FK ไปที่
    blacklist_numbers แทน (3NF) เบอร์จึงถูกเก็บที่เดียว
    """
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    blacklist_number_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("blacklist_numbers.id", ondelete="CASCADE"), nullable=False
    )
    reported_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    risk_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    blacklist_number: Mapped["BlacklistNumber"] = relationship(back_populates="reports")
    reporter: Mapped["User | None"] = relationship(back_populates="reports")
    categories: Mapped[list["ScamCategory"]] = relationship(
        secondary=report_categories, back_populates="reports", order_by="ScamCategory.id"
    )

    # ---- ค่าที่ใช้ตอน serialize (ต้อง eager-load relationship ไว้ก่อน ไม่งั้นเกิด N+1) ----
    @property
    def phone_number(self) -> str:
        return self.blacklist_number.phone_number

    @property
    def reporter_username(self) -> str | None:
        return self.reporter.username if self.reporter else None


# ---------- INDEXES ----------
# Postgres "ไม่" สร้าง index ให้ foreign key อัตโนมัติ (ต่างจาก MySQL) ต้องสร้างเอง
# [IDX-4] (blacklist_number_id, created_at DESC): รายการ report ล่าสุดของเบอร์หนึ่ง
#   (หน้า detail ของ blacklist) + ทำให้ ON DELETE CASCADE ไม่ต้อง Seq Scan ทั้งตาราง
Index("ix_reports_blacklist_created", Report.blacklist_number_id, Report.created_at.desc())
# [IDX-5] (reported_by, created_at DESC): "รายงานของฉัน" (/reports/me) เรียงใหม่สุดก่อน
#   + ทำให้ ON DELETE SET NULL ตอนลบ user ไม่ต้อง Seq Scan
Index("ix_reports_reporter_created", Report.reported_by, Report.created_at.desc())
