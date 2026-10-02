import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.validators import StrongPassword, strip_text
from app.models.user import UserRole

# ---------- Request schemas ----------

USERNAME_PATTERN = r"^[A-Za-z0-9._-]+$"


class UserRegister(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=3, max_length=50, pattern=USERNAME_PATTERN,
                          examples=["officer.somchai"])
    email: EmailStr
    password: StrongPassword = Field(min_length=8, max_length=72)  # bcrypt รับได้สูงสุด 72 bytes
    full_name: str | None = Field(default=None, max_length=150)
    role: UserRole = UserRole.gov

    @field_validator("role")
    @classmethod
    def _no_self_admin(cls, v: UserRole) -> UserRole:
        # ห้ามสมัครเป็น admin เอง (privilege escalation) — admin ต้องถูกตั้งโดย admin คนอื่นหรือ seed
        if v == UserRole.admin:
            raise ValueError("ไม่สามารถสมัครด้วยสิทธิ์ admin ได้")
        return v

    @field_validator("full_name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        return strip_text(v)


class UserLogin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: StrongPassword = Field(min_length=8, max_length=72)


class UserUpdate(BaseModel):
    # ทุก field เป็น optional เพื่อรองรับ partial update ผ่าน PUT
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=150)
    role: UserRole | None = None
    is_active: bool | None = None
    auto_notify: bool | None = None
    password: StrongPassword | None = Field(default=None, min_length=8, max_length=72)


# ---------- Response schemas ----------

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str  # ข้อมูลขาออกไม่ต้อง validate ซ้ำ (validate แล้วตอนรับเข้า)
    full_name: str | None
    role: UserRole
    role_label: str
    is_active: bool
    auto_notify: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PaginatedUsers(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserOut]


class UsernameAvailability(BaseModel):
    username: str
    available: bool
