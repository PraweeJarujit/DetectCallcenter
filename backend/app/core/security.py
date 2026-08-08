"""
รวมฟังก์ชันด้านความปลอดภัย:
- การ hash / verify รหัสผ่านด้วย bcrypt (ผ่าน passlib)
- การสร้าง / ตรวจสอบ JWT access token
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """
    subject มักเป็น user id (เก็บใน claim 'sub' ตาม convention ของ JWT)
    extra_claims ใช้แนบข้อมูลเสริม เช่น role เพื่อลด query ตอนเช็คสิทธิ์
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    # jti (JWT ID) ที่ไม่ซ้ำกัน ใช้สำหรับทำ token blacklist ตอน logout
    to_encode = {"sub": str(subject), "iat": now, "exp": expire, "jti": uuid.uuid4().hex}
    if extra_claims:
        to_encode.update(extra_claims)
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
