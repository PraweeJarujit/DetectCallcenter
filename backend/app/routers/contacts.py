"""
Router: Emergency Contacts (CRUD เต็มรูปแบบ GET/POST/PUT/DELETE ให้หน้า Settings)
ทุก endpoint เห็น/แก้ได้เฉพาะผู้ติดต่อของตัวเอง
"""
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.emergency_contact import EmergencyContact
from app.models.user import User
from app.schemas.contact import ContactCreate, ContactOut, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])

MAX_CONTACTS = 10


def _get_own_contact(db: Session, contact_id: uuid.UUID, user: User) -> EmergencyContact:
    contact = db.get(EmergencyContact, contact_id)
    # คืน 404 แม้เป็นของคนอื่น (ไม่ใช่ 403) เพื่อไม่บอกใบ้ว่ามี id นี้อยู่จริง (ป้องกัน IDOR enumeration)
    if contact is None or contact.user_id != user.id:
        raise NotFoundError("ไม่พบผู้ติดต่อ")
    return contact


def _ensure_unique_phone(db: Session, user: User, phone: str, exclude_id: uuid.UUID | None = None):
    q = select(EmergencyContact.id).where(
        EmergencyContact.user_id == user.id, EmergencyContact.phone_number == phone
    )
    if exclude_id:
        q = q.where(EmergencyContact.id != exclude_id)
    if db.scalar(q) is not None:
        raise ConflictError("มีผู้ติดต่อเบอร์นี้อยู่แล้ว")


@router.get("", response_model=list[ContactOut])
def list_contacts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.scalars(
        select(EmergencyContact)
        .where(EmergencyContact.user_id == current_user.id)  # IDX-9
        .order_by(EmergencyContact.created_at)
    ).all()


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.scalar(
        select(func.count()).select_from(EmergencyContact).where(EmergencyContact.user_id == current_user.id)
    )
    if count >= MAX_CONTACTS:
        raise BadRequestError(f"เพิ่มผู้ติดต่อฉุกเฉินได้สูงสุด {MAX_CONTACTS} คน")
    _ensure_unique_phone(db, current_user, payload.phone_number)

    contact = EmergencyContact(user_id=current_user.id, name=payload.name, phone_number=payload.phone_number)
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: uuid.UUID,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = _get_own_contact(db, contact_id, current_user)
    data = payload.model_dump(exclude_unset=True, exclude_none=True)
    if not data:
        raise BadRequestError("ไม่มีข้อมูลที่ต้องแก้ไข")
    if "phone_number" in data:
        _ensure_unique_phone(db, current_user, data["phone_number"], exclude_id=contact.id)
    for field, value in data.items():
        setattr(contact, field, value)
    db.commit()
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contact = _get_own_contact(db, contact_id, current_user)
    db.delete(contact)
    db.commit()
    return {"success": True, "message": "ลบผู้ติดต่อแล้ว"}
