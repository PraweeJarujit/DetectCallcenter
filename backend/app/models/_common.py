from datetime import datetime, timezone


def utcnow() -> datetime:
    """เวลา UTC แบบมี timezone — ใช้เป็น default ฝั่ง Python ให้ทุก DB (Postgres/SQLite) ได้ค่าเดียวกัน"""
    return datetime.now(timezone.utc)
