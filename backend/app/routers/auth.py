"""
Router: Authentication
/register, /login, /logout, /change-password
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ConflictError,
    PermissionDeniedError,
    TooManyRequestsError,
)
from app.core.rate_limit import SlidingWindowLimiter
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.database import get_db
from app.dependencies import bearer_scheme, get_current_user
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.schemas.user import ChangePasswordRequest, TokenResponse, UserLogin, UserOut, UserRegister

router = APIRouter(tags=["auth"])
logger = logging.getLogger("app.auth")

login_limiter = SlidingWindowLimiter(settings.LOGIN_MAX_ATTEMPTS, settings.LOGIN_WINDOW_SECONDS)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister, db: Session = Depends(get_db)):
    # query เดียวเช็คทั้ง username และ email (ใช้ unique index ทั้ง 2 ตัวผ่าน BitmapOr)
    existing = db.execute(
        select(User.username, User.email).where(
            or_(User.username == payload.username, User.email == payload.email)
        )
    ).first()
    if existing:
        if existing.username == payload.username:
            raise ConflictError("Username นี้ถูกใช้งานแล้ว")
        raise ConflictError("อีเมลนี้ถูกใช้งานแล้ว")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # กันกรณี 2 request สมัครชื่อเดียวกันพร้อมกัน (race condition) — unique constraint คือด่านสุดท้าย
        db.rollback()
        raise ConflictError("Username หรืออีเมลนี้ถูกใช้งานแล้ว") from None
    db.refresh(user)
    logger.info("user registered: %s (%s)", user.username, user.role.value)
    return user


@router.post("/login", response_model=TokenResponse)
def login(payload: UserLogin, request: Request, db: Session = Depends(get_db)):
    client_ip = (request.client.host if request.client else None) or "unknown"
    # นับต่อ username (ไม่ผูกกับ IP) — IP ปลอมได้ง่ายผ่าน X-Forwarded-For และผู้โจมตีเปลี่ยน IP ได้
    # ข้อแลกเปลี่ยน: คนอื่นทำให้ username หนึ่งถูกล็อกชั่วคราวได้ (แค่ LOGIN_WINDOW_SECONDS วินาที)
    limiter_key = payload.username.lower()
    if login_limiter.is_blocked(limiter_key):
        raise TooManyRequestsError(
            f"พยายามเข้าสู่ระบบผิดเกิน {settings.LOGIN_MAX_ATTEMPTS} ครั้ง "
            f"กรุณารอ {settings.LOGIN_WINDOW_SECONDS} วินาทีแล้วลองใหม่",
            headers={"Retry-After": str(settings.LOGIN_WINDOW_SECONDS)},
        )

    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.hashed_password):
        login_limiter.hit(limiter_key)
        logger.warning("failed login for username=%s from %s", payload.username, client_ip)
        # ข้อความเดียวกันทั้ง "ไม่มี user" และ "รหัสผิด" — ไม่บอกใบ้ว่ามี username นี้อยู่จริงไหม
        raise AuthenticationError("Username หรือ password ไม่ถูกต้อง")
    if not user.is_active:
        raise PermissionDeniedError("บัญชีนี้ถูกระงับการใช้งาน")

    login_limiter.reset(limiter_key)
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return TokenResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/logout")
def logout(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """
    เพิกถอน (revoke) token ปัจจุบันโดยบันทึก jti ลง blacklist
    ทำให้ token นี้ใช้เรียก endpoint ที่ต้อง login ไม่ได้อีก แม้จะยังไม่หมดอายุ
    """
    payload = decode_access_token(credentials.credentials) if credentials else None
    if payload is None or "jti" not in payload:
        raise AuthenticationError("Token ไม่ถูกต้อง")

    already = db.scalar(select(TokenBlacklist.id).where(TokenBlacklist.jti == payload["jti"]))
    if not already:
        expires_at = (
            datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None
        )
        db.add(TokenBlacklist(jti=payload["jti"], expires_at=expires_at))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # logout ซ้ำพร้อมกัน — ถือว่าสำเร็จ

    return {"success": True, "message": "ออกจากระบบสำเร็จ"}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.old_password, current_user.hashed_password):
        raise BadRequestError("รหัสผ่านเดิมไม่ถูกต้อง")
    if payload.old_password == payload.new_password:
        raise BadRequestError("รหัสผ่านใหม่ต้องไม่ซ้ำกับรหัสผ่านเดิม")

    current_user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"success": True, "message": "เปลี่ยนรหัสผ่านสำเร็จ"}
