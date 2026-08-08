"""
Dependency กลางสำหรับตรวจสอบสิทธิ์ผู้ใช้จาก JWT Bearer token
- get_current_user: ตรวจ token, decode, เช็ค blacklist, โหลด user จาก DB
- require_admin: ใช้ต่อจาก get_current_user เพื่อจำกัด endpoint เฉพาะ admin
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User, UserRole

bearer_scheme = HTTPBearer(auto_error=True)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="ไม่สามารถยืนยันตัวตนได้ (invalid or expired token)",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    jti = payload.get("jti")
    user_id = payload.get("sub")
    if user_id is None or jti is None:
        raise credentials_exception

    # เช็คว่า token ถูก logout (revoke) ไปแล้วหรือยัง
    revoked = db.query(TokenBlacklist).filter(TokenBlacklist.jti == jti).first()
    if revoked is not None:
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.is_active:
        raise credentials_exception

    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ต้องใช้สิทธิ์ผู้ดูแลระบบ (admin) เท่านั้น",
        )
    return current_user
