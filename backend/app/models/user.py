import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models._common import utcnow

if TYPE_CHECKING:
    from app.models.call_log import CallLog
    from app.models.emergency_contact import EmergencyContact
    from app.models.payment import Payment
    from app.models.report import Report


class UserRole(str, enum.Enum):
    # เว็บขายสมาชิกให้บุคคลทั่วไป (ไม่ขายองค์กรแล้ว) -> เหลือ 2 บทบาท
    # สิทธิ์ฟรี / Premium ไม่ใช่ role แต่ดูจาก premium_until (หมดอายุเองโดยไม่ต้องมี job มาเปลี่ยน role)
    member = "member"    # ผู้ใช้ทั่วไป
    admin = "admin"      # ผู้ดูแลระบบ


ROLE_LABELS = {
    UserRole.member: "สมาชิก",
    UserRole.admin: "ผู้ดูแลระบบ",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # unique=True สร้าง unique index ให้อยู่แล้ว -> ใช้กับ login / check-username (ค้นแบบ = ตรงตัว)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # native_enum=False -> เก็บเป็น VARCHAR + CHECK constraint (migrate ง่ายกว่า ENUM type ของ Postgres)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=10, validate_strings=True),
        default=UserRole.member, nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # การตั้งค่า "แจ้งเตือนผู้ติดต่อฉุกเฉินอัตโนมัติ" ในหน้า Settings
    auto_notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---------- สมาชิก Premium (59 บาท/เดือน) ----------
    # เก็บวันหมดอายุไว้ที่ users โดยตรง เพื่อเช็คสิทธิ์ได้ทันทีทุก request โดยไม่ต้อง JOIN payments
    premium_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow, nullable=False
    )

    # ---------- Relationships (One-to-Many จากฝั่ง User) ----------
    reports: Mapped[list["Report"]] = relationship(back_populates="reporter", passive_deletes=True)
    call_logs: Mapped[list["CallLog"]] = relationship(back_populates="user", passive_deletes=True)
    emergency_contacts: Mapped[list["EmergencyContact"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
        order_by="EmergencyContact.created_at",
    )
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, str(self.role))

    @property
    def is_premium(self) -> bool:
        if self.role == UserRole.admin:
            return True
        if self.premium_until is None:
            return False
        until = self.premium_until
        if until.tzinfo is None:  # SQLite คืนค่าแบบไม่มี timezone
            until = until.replace(tzinfo=timezone.utc)
        return until > datetime.now(timezone.utc)

    @property
    def plan(self) -> str:
        return "premium" if self.is_premium else "free"
