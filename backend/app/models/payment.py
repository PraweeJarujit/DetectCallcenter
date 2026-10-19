import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow

if TYPE_CHECKING:
    from app.models.user import User


class PaymentStatus(str, enum.Enum):
    pending = "pending"      # สร้างรายการชำระแล้ว รอผู้ใช้จ่าย
    paid = "paid"            # ชำระสำเร็จ -> ต่ออายุ premium_until แล้ว
    expired = "expired"      # ไม่ได้จ่ายภายในเวลาที่กำหนด
    cancelled = "cancelled"  # ผู้ใช้ยกเลิกเอง


class Payment(Base):
    """
    ประวัติการชำระค่าสมาชิก Premium (users 1──N payments)

    provider = "mock" คือระบบจำลอง (ยังไม่ได้ต่อ payment gateway จริง)
    เมื่อเปิดใช้ gateway จริง (เช่น Stripe / Omise) ให้เก็บ id ของฝั่ง gateway ใน provider_ref
    และเปลี่ยน endpoint confirm เป็น webhook ที่ gateway เรียกกลับมา
    """
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_baht: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=False, length=10, validate_strings=True),
        default=PaymentStatus.pending, nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), default="mock", nullable=False)
    provider_ref: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    method: Mapped[str] = mapped_column(String(20), default="promptpay", nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="payments")


# [IDX-10] ประวัติการชำระของผู้ใช้ เรียงล่าสุดก่อน (หน้า "บัญชีของฉัน") + รองรับ FK ON DELETE CASCADE
Index("ix_payments_user_created", Payment.user_id, Payment.created_at.desc())
