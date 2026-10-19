import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow


class ContactStatus(str, enum.Enum):
    new = "new"
    handled = "handled"


class ContactMessage(Base):
    """ข้อความจากฟอร์ม "ติดต่อเรา" บนหน้าเว็บ (ไม่ต้อง login) — admin อ่านและกดว่าจัดการแล้ว"""
    __tablename__ = "contact_messages"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    topic: Mapped[str] = mapped_column(String(30), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, native_enum=False, length=10, validate_strings=True),
        default=ContactStatus.new, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# [IDX-11] กล่องข้อความของ admin: กรองตามสถานะ เรียงใหม่สุดก่อน
Index("ix_contact_messages_status_created", ContactMessage.status, ContactMessage.created_at.desc())
