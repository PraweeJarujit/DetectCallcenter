"""
ตั้งค่าการเชื่อมต่อฐานข้อมูลด้วย SQLAlchemy
- engine: การเชื่อมต่อจริงไปยัง Postgres (อ่าน DATABASE_URL จาก settings)
- SessionLocal: factory สำหรับสร้าง session ต่อ request
- get_db(): dependency สำหรับ inject session เข้า endpoint แล้วปิด session อัตโนมัติ
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
