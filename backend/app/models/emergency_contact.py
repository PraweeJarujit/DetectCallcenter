import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow

if TYPE_CHECKING:
    from app.models.user import User


class EmergencyContact(Base):
    """ผู้ติดต่อฉุกเฉินของผู้ใช้ (User 1 ── N EmergencyContact) — หน้า Settings ทำ CRUD ตารางนี้"""
    __tablename__ = "emergency_contacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="emergency_contacts")


# [IDX-9] user_id: ดึงรายชื่อผู้ติดต่อของตัวเอง (WHERE user_id = :me) + FK ON DELETE CASCADE
Index("ix_emergency_contacts_user", EmergencyContact.user_id)
