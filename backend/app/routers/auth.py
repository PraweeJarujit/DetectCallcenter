"""
Router: Authentication
/register, /login, /logout, /change-password
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.dependencies import get_current_user
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, TokenResponse, UserLogin, UserOut, UserRegister

router = APIRouter(tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=True)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username นี้ถูกใช้งานแล้ว")
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "อีเมลนี้ถูกใช้งานแล้ว")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Username หรือ password ไม่ถูกต้อง")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "บัญชีนี้ถูกระงับการใช้งาน")

    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return TokenResponse(access_token=token, user=user)


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    เพิกถอน (revoke) token ปัจจุบันโดยบันทึก jti ลง blacklist
    ทำให้ token นี้ใช้เรียก endpoint ที่ต้อง login ไม่ได้อีก แม้จะยังไม่หมดอายุ
    """
    payload = decode_access_token(credentials.credentials)
    if payload is None or "jti" not in payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ไม่ถูกต้อง")

    already = db.query(TokenBlacklist).filter(TokenBlacklist.jti == payload["jti"]).first()
    if not already:
        db.add(TokenBlacklist(jti=payload["jti"]))
        db.commit()

    return {"success": True, "message": "ออกจากระบบสำเร็จ"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "รหัสผ่านเดิมไม่ถูกต้อง")

    current_user.hashed_password = hash_password(payload.new_password)
    db.add(current_user)
    db.commit()
    return {"success": True, "message": "เปลี่ยนรหัสผ่านสำเร็จ"}
