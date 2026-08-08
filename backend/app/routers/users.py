"""
Router: User Management
/me, /users/{id}, /users, /users/{id} (PUT/DELETE), /check-username/{name}
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.schemas.user import PaginatedUsers, UserOut, UserUpdate, UsernameAvailability

router = APIRouter(tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/check-username/{name}", response_model=UsernameAvailability)
def check_username(name: str, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.username == name).first() is not None
    return UsernameAvailability(username=name, available=not exists)


@router.get("/users", response_model=PaginatedUsers)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=settings.DEFAULT_PAGE_SIZE, ge=1, le=settings.MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # ต้อง login ถึงจะดูรายชื่อ user ทั้งหมดได้
):
    query = db.query(User).order_by(User.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedUsers(total=total, page=page, page_size=page_size, items=items)


@router.get("/users/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้งาน")
    return user


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # เจ้าของบัญชีแก้ไขข้อมูลตัวเองได้ / admin แก้ไขของใครก็ได้
    if current_user.id != user_id and current_user.role.value != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ไม่มีสิทธิ์แก้ไขข้อมูลผู้ใช้งานนี้")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้งาน")

    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.hashed_password = hash_password(password)
    # เฉพาะ admin เท่านั้นที่แก้ role / is_active ของคนอื่นได้
    if current_user.role.value != "admin":
        data.pop("role", None)
        data.pop("is_active", None)

    for field, value in data.items():
        setattr(user, field, value)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_200_OK)
def delete_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),  # ลบ user ได้เฉพาะ admin
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ไม่พบผู้ใช้งาน")

    db.delete(user)
    db.commit()
    return {"success": True, "message": "ลบผู้ใช้งานสำเร็จ"}
