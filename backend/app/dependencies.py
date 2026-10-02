"""
Dependency กลางสำหรับตรวจสอบสิทธิ์ผู้ใช้จาก JWT Bearer token
- get_current_user: ตรวจ token, decode, เช็ค blacklist, โหลด user จาก DB
- get_current_user_optional: เหมือนกันแต่ไม่บังคับ login (คืน None ถ้าไม่มี token)
- require_admin: ใช้ต่อจาก get_current_user เพื่อจำกัด endpoint เฉพาะ admin
"""
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.database import get_db
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User, UserRole

# auto_error=False: ไม่ให้ FastAPI ตอบ 403 "Not authenticated" เอง
# เราตอบ 401 + WWW-Authenticate ตามมาตรฐาน HTTP แทน
bearer_scheme = HTTPBearer(auto_error=False)


def _user_from_token(token: str, db: Session) -> User:
    payload = decode_access_token(token)
    if payload is None:
        raise AuthenticationError()

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if user_id is None or jti is None:
        raise AuthenticationError()

    # เช็คว่า token ถูก logout (revoke) ไปแล้วหรือยัง — ค้นด้วย unique index ของ jti
    revoked = db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.jti == jti))
    if revoked is not None:
        raise AuthenticationError("Token นี้ถูกออกจากระบบไปแล้ว กรุณาเข้าสู่ระบบใหม่")

    try:
        user = db.get(User, uuid.UUID(user_id))
    except ValueError:
        raise AuthenticationError() from None
    if user is None or not user.is_active:
        raise AuthenticationError()
    return user


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("กรุณาเข้าสู่ระบบก่อนใช้งาน")
    return _user_from_token(credentials.credentials, db)


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    return _user_from_token(credentials.credentials, db)


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise PermissionDeniedError("ต้องใช้สิทธิ์ผู้ดูแลระบบ (admin) เท่านั้น")
    return current_user
