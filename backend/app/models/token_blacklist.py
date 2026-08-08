"""
JWT เป็น stateless โดยธรรมชาติ ดังนั้นการ "logout" ที่แท้จริงต้องมีที่เก็บ token
ที่ถูกเพิกถอนแล้ว (revoked) ตารางนี้เก็บ jti (JWT ID) ของ token ที่ logout ไปแล้ว
Dependency get_current_user จะเช็คตารางนี้ทุกครั้งก่อนเชื่อถือ token
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class TokenBlacklist(Base):
    __tablename__ = "token_blacklist"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
