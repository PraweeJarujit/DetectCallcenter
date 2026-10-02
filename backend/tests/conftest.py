"""
Fixtures กลางของชุดทดสอบ

ค่าเริ่มต้นใช้ SQLite (ไม่ต้องมี Docker) — อยากทดสอบบน Postgres จริง ให้ตั้ง
    TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/test_db pytest
(ฐานข้อมูลนั้นจะถูกล้างทุก test — ห้ามชี้ไปที่ฐานข้อมูลจริง!)
"""
import os
import tempfile

# ต้องตั้ง env ก่อน import app (settings / engine ถูกสร้างตอน import)
_tmpdir = tempfile.mkdtemp(prefix="dcc-test-")
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["VOICEGUARD_AI_URL"] = "http://127.0.0.1:9"  # พอร์ตที่ไม่มีใครฟัง -> fallback mock ทันที
os.environ["LOGIN_MAX_ATTEMPTS"] = "3"
os.environ["LOG_LEVEL"] = "WARNING"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.models.user import UserRole  # noqa: E402
from app.routers.auth import login_limiter  # noqa: E402
from app.seed import seed_categories  # noqa: E402

PASSWORD = "Passw0rd123"


@pytest.fixture(scope="session", autouse=True)
def _create_schema():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_db():
    """ล้างข้อมูลทุกตารางก่อนแต่ละ test แล้วใส่ scam_categories ตั้งต้น"""
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())
    with SessionLocal() as db:
        seed_categories(db)
    login_limiter.reset()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def make_user(db):
    def _make(username="officer", role=UserRole.gov, password=PASSWORD, is_active=True, email=None):
        user = User(
            username=username,
            email=email or f"{username}@example.com",
            hashed_password=hash_password(password),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    return _make


def auth_header(user: User) -> dict:
    token = create_access_token(subject=str(user.id), extra_claims={"role": user.role.value})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def user(make_user):
    return make_user("officer")


@pytest.fixture
def admin(make_user):
    return make_user("admin", role=UserRole.admin)


@pytest.fixture
def user_headers(user):
    return auth_header(user)


@pytest.fixture
def admin_headers(admin):
    return auth_header(admin)


class QueryCounter:
    """นับจำนวน SQL statement ที่ยิงไปยัง DB — ใช้พิสูจน์ว่าไม่มีปัญหา N+1"""

    def __init__(self):
        self.count = 0
        self.statements: list[str] = []

    def __call__(self, conn, cursor, statement, *args):
        self.count += 1
        self.statements.append(statement)


@pytest.fixture
def count_queries():
    counter = QueryCounter()
    event.listen(engine, "before_cursor_execute", counter)
    yield counter
    event.remove(engine, "before_cursor_execute", counter)
