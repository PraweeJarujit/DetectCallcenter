"""
JWT เป็น stateless โดยธรรมชาติ ดังนั้นการ "logout" ที่แท้จริงต้องมีที่เก็บ token
ที่ถูกเพิกถอนแล้ว (revoked) ตารางนี้เก็บ jti (JWT ID) ของ token ที่ logout ไปแล้ว
Dependency get_current_user จะเช็คตารางนี้ทุกครั้งก่อนเชื่อถือ token
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # unique -> มี unique index ให้อัตโนมัติ: ทุก request ที่ login แล้วจะค้น jti = ? ที่นี่ (query ที่ถี่ที่สุดในระบบ)
    jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # เวลาหมดอายุของ token เดิม — หลังเวลานี้ลบแถวทิ้งได้ (token หมดอายุเองแล้ว) ตารางจึงไม่โตไม่สิ้นสุด
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
