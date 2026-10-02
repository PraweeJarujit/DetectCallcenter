from typing import TYPE_CHECKING

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.report import Report


class ScamCategory(Base):
    """ตาราง lookup รูปแบบการหลอกลวง (ฝั่ง "N" อีกข้างของ Many-to-Many กับ Report)"""
    __tablename__ = "scam_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    reports: Mapped[list["Report"]] = relationship(
        secondary="report_categories", back_populates="categories"
    )


# ค่าเริ่มต้น (ถูก insert ใน migration 0001 และใน seed สำหรับ test)
DEFAULT_CATEGORIES = [
    ("impersonate_police", "แอบอ้างเป็นตำรวจ/DSI"),
    ("impersonate_bank", "แอบอ้างเป็นเจ้าหน้าที่ธนาคาร"),
    ("parcel", "พัสดุผิดกฎหมาย/ค้างส่ง"),
    ("investment", "ชวนลงทุนผลตอบแทนสูง"),
    ("loan", "เงินกู้ออนไลน์"),
    ("refund", "คืนเงิน/ภาษี/ค่าไฟ"),
    ("voice_clone", "ใช้เสียงสังเคราะห์เลียนแบบคนรู้จัก"),
    ("other", "อื่น ๆ"),
]
