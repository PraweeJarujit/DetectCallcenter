import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class NumberStatus(str, enum.Enum):
    safe = "safe"
    suspect = "suspect"
    high_risk = "high_risk"


class BlacklistNumber(Base):
    """
    เบอร์โทรที่เคยถูก report หรือระบบตรวจพบว่ามีความเสี่ยง
    report_count ใช้สะสมจำนวนครั้งที่ถูกแจ้งเข้ามา เพื่อคำนวณ status
    """
    __tablename__ = "blacklist_numbers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    status: Mapped[NumberStatus] = mapped_column(Enum(NumberStatus), default=NumberStatus.suspect)
    risk_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    report_count: Mapped[int] = mapped_column(Integer, default=0)

    first_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
