"""
Custom validators ที่ใช้ซ้ำใน Pydantic schemas (Week 3-4: Custom validators)

normalize_phone():  "081-234-5678" / "+66 81 234 5678" / "081 234 5678"  ->  "0812345678"
                    เก็บรูปแบบเดียวใน DB เพื่อให้ค้นหาด้วย index ได้ตรง (ไม่ต้องใช้ function บน column)
"""
import re
from typing import Annotated

from pydantic import AfterValidator

_SEPARATORS = re.compile(r"[\s\-().]")
_THAI_NUMBER = re.compile(r"^0\d{8,9}$")      # 02xxxxxxx (9 หลัก) หรือ 08xxxxxxxx (10 หลัก)
_HOTLINE = re.compile(r"^1\d{3}$")            # สายด่วน 4 หลัก เช่น 1441, 1599


def normalize_phone(value: str) -> str:
    v = _SEPARATORS.sub("", value.strip())
    if v.startswith("+66"):
        v = "0" + v[3:]
    elif v.startswith("66") and len(v) in (10, 11):
        v = "0" + v[2:]
    return v


def validate_thai_phone(value: str) -> str:
    v = normalize_phone(value)
    if not _THAI_NUMBER.match(v):
        raise ValueError("เบอร์โทรต้องเป็นเบอร์ไทย 9-10 หลัก ขึ้นต้นด้วย 0 (เช่น 0812345678)")
    return v


def validate_contact_phone(value: str) -> str:
    """ผู้ติดต่อฉุกเฉินอนุญาตสายด่วน 4 หลักด้วย (เช่น 1441 ตำรวจไซเบอร์)"""
    v = normalize_phone(value)
    if not (_THAI_NUMBER.match(v) or _HOTLINE.match(v)):
        raise ValueError("เบอร์โทรต้องเป็นเบอร์ไทย 9-10 หลัก หรือสายด่วน 4 หลัก")
    return v


def validate_phone_prefix(value: str) -> str:
    """ใช้กับช่องค้นหา: อนุญาตเฉพาะตัวเลข เพื่อให้ LIKE 'prefix%' ปลอดภัยและใช้ index ได้"""
    v = normalize_phone(value)
    if not v.isdigit() or not (1 <= len(v) <= 10):
        raise ValueError("คำค้นหาต้องเป็นตัวเลข 1-10 หลัก")
    return v


def validate_password_strength(value: str) -> str:
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("รหัสผ่านต้องมีทั้งตัวอักษรและตัวเลข")
    return value


def strip_text(value: str | None) -> str | None:
    if value is None:
        return None
    v = value.strip()
    return v or None


ThaiPhone = Annotated[str, AfterValidator(validate_thai_phone)]
ContactPhone = Annotated[str, AfterValidator(validate_contact_phone)]
StrongPassword = Annotated[str, AfterValidator(validate_password_strength)]
