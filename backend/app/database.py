"""
ตั้งค่าการเชื่อมต่อฐานข้อมูลด้วย SQLAlchemy
- engine: การเชื่อมต่อจริงไปยัง Postgres (อ่าน DATABASE_URL จาก settings)
- SessionLocal: factory สำหรับสร้าง session ต่อ request
- get_db(): dependency สำหรับ inject session เข้า endpoint แล้วปิด session อัตโนมัติ
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings


def normalize_db_url(url: str) -> str:
    # ผู้ให้บริการ cloud (Render/Railway/Heroku) มักให้ URL แบบ postgres:// ซึ่ง SQLAlchemy 2 ไม่รับ
    if url.startswith("postgres://"):
        url = "postgresql+psycopg2://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalize_db_url(settings.DATABASE_URL)

_engine_kwargs: dict = {"pool_pre_ping": True, "echo": settings.DB_ECHO}
if DATABASE_URL.startswith("postgresql"):
    _engine_kwargs.update(pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW)

engine = create_engine(DATABASE_URL, **_engine_kwargs)

if DATABASE_URL.startswith("sqlite"):
    # SQLite (ใช้ตอนรัน unit test) ปิด foreign key ไว้เป็นค่าเริ่มต้น — เปิดให้ ON DELETE CASCADE ทำงานเหมือน Postgres
    @event.listens_for(engine, "connect")
    def _sqlite_fk_on(dbapi_conn, _):  # pragma: no cover - ขึ้นกับ DB ที่ใช้
        dbapi_conn.execute("PRAGMA foreign_keys=ON")


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
