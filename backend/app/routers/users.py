"""
Router: User Management
/me, /users/{id}, /users, /users/{id} (PUT/DELETE), /check-username/{name}
"""
import uuid

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError
from app.core.security import hash_password
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User, UserRole
from app.schemas.user import PaginatedUsers, UserOut, UsernameAvailability, UserUpdate

router = APIRouter(tags=["users"])


def _get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise NotFoundError("ไม่พบผู้ใช้งาน")
    return user


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/check-username/{name}", response_model=UsernameAvailability)
def check_username(
    name: str = Path(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$"),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(User.id).where(User.username == name)) is not None
    return UsernameAvailability(username=name, available=not exists)


@router.get("/users", response_model=PaginatedUsers)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # รายชื่อผู้ใช้ทั้งหมด (มีอีเมล) ให้เฉพาะ admin
):
    total = db.scalar(select(func.count()).select_from(User))
    items = db.scalars(
        select(User).order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size).limit(page_size)
    ).all()
    return PaginatedUsers(total=total, page=page, page_size=page_size, items=items)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id and current_user.role != UserRole.admin:
        raise PermissionDeniedError("ไม่มีสิทธิ์ดูข้อมูลผู้ใช้งานนี้")
    return _get_user_or_404(db, user_id)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_admin = current_user.role == UserRole.admin
    # เจ้าของบัญชีแก้ไขข้อมูลตัวเองได้ / admin แก้ไขของใครก็ได้
    if current_user.id != user_id and not is_admin:
        raise PermissionDeniedError("ไม่มีสิทธิ์แก้ไขข้อมูลผู้ใช้งานนี้")

    user = _get_user_or_404(db, user_id)
    data = payload.model_dump(exclude_unset=True)

    # เฉพาะ admin เท่านั้นที่แก้ role / is_active ได้
    if not is_admin and ({"role", "is_active"} & data.keys()):
        raise PermissionDeniedError("เฉพาะ admin เท่านั้นที่แก้ไข role หรือสถานะบัญชีได้")
    if is_admin and user.id == current_user.id and data.get("is_active") is False:
        raise BadRequestError("ไม่สามารถระงับบัญชีของตัวเองได้")

    password = data.pop("password", None)
    if password:
        user.hashed_password = hash_password(password)
    for field, value in data.items():
        if value is None and field in ("email", "role", "is_active", "auto_notify"):
            continue  # ไม่อนุญาตให้ตั้ง field ที่ NOT NULL เป็น null
        setattr(user, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError("อีเมลนี้ถูกใช้งานแล้ว") from None
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # ลบ user ได้เฉพาะ admin
):
    if user_id == current_user.id:
        raise BadRequestError("ไม่สามารถลบบัญชีของตัวเองได้")
    user = _get_user_or_404(db, user_id)
    db.delete(user)
    db.commit()
    return {"success": True, "message": "ลบผู้ใช้งานสำเร็จ"}
