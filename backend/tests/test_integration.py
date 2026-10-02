"""
Integration tests: flow หลายขั้นตอน, รูปแบบ error กลาง, security headers, N+1, seed
"""
import random

from sqlalchemy import func, select

from app.models import BlacklistNumber, CallLog, Report, ScamCategory, User
from app.seed import main as seed_main
from app.seed import seed_categories, seed_demo


def test_full_user_journey(client):
    """สมัคร -> login -> ตรวจเบอร์ -> แจ้ง report -> ดู dashboard -> เพิ่มผู้ติดต่อ -> logout"""
    assert client.post("/api/register", json={"username": "jane", "email": "jane@example.com",
                                              "password": "Jane12345", "role": "telco"}).status_code == 201
    token = client.post("/api/login", json={"username": "jane", "password": "Jane12345"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    assert client.post("/api/detect/number", headers=h, json={"phone_number": "0899999999"}).json()["status"] == "safe"
    client.post("/api/report", headers=h, json={"phone_number": "0899999999", "risk_score": 92,
                                               "category_codes": ["investment"]})
    assert client.post("/api/detect/number", json={"phone_number": "0899999999"}).json()["status"] == "high_risk"
    stats = client.get("/api/calls/stats", headers=h).json()
    assert stats["checked_today"] == 2
    assert client.post("/api/contacts", headers=h, json={"name": "พี่", "phone_number": "0811112222"}).status_code == 201
    assert client.post("/api/logout", headers=h).status_code == 200
    assert client.get("/api/contacts", headers=h).status_code == 401


def test_error_format_and_headers(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False and body["error"]["code"] == "NOT_FOUND" and body["request_id"]
    assert r.headers["X-Request-ID"] == body["request_id"]

    r = client.get("/api/health", headers={"X-Request-ID": "trace-123"})
    assert r.json() == {"status": "ok", "database": "ok"}
    assert r.headers["X-Request-ID"] == "trace-123"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert "X-Response-Time-ms" in r.headers

    assert client.delete("/api/health").status_code == 405
    assert "Content-Security-Policy" not in client.get("/docs").headers


def test_cors_only_allows_configured_origins(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:3000",
                                                "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/api/health", headers={"Origin": "https://evil.example",
                                                 "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers


def test_unhandled_error_hides_details():
    from fastapi.testclient import TestClient

    from app.main import app

    @app.get("/api/_boom_test")
    def boom():
        raise RuntimeError("secret internal detail")

    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.get("/api/_boom_test")
        assert r.status_code == 500
        assert r.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "secret" not in r.text
    finally:
        app.router.routes = [rt for rt in app.router.routes if getattr(rt, "path", "") != "/api/_boom_test"]


def test_no_n_plus_one_in_blacklist_detail(client, user_headers, count_queries):
    """จำนวน query ต้องคงที่ ไม่ว่าเบอร์นั้นจะมี report กี่รายการ (selectinload/joinedload)"""
    def queries_for(n_reports, phone):
        for _ in range(n_reports):
            client.post("/api/report", headers=user_headers,
                        json={"phone_number": phone, "risk_score": 80, "category_codes": ["loan", "parcel"]})
        count_queries.count = 0
        r = client.get(f"/api/blacklist/{phone}", headers=user_headers)
        assert len(r.json()["reports"]) == n_reports
        return count_queries.count

    assert queries_for(2, "0811111111") == queries_for(15, "0822222222")


def test_no_n_plus_one_in_my_reports(client, user_headers, count_queries):
    def queries_for(n):
        for i in range(n):
            client.post("/api/report", headers=user_headers,
                        json={"phone_number": f"08100000{i:02d}", "risk_score": 50, "category_codes": ["loan"]})
        count_queries.count = 0
        client.get("/api/reports/me?page_size=100", headers=user_headers)
        return count_queries.count

    few = queries_for(2)
    assert queries_for(20) == few


def test_seed_demo_is_idempotent(db, monkeypatch):
    assert seed_categories(db) == 0  # ใส่ไว้แล้วจาก fixture
    assert seed_demo(db, random.Random(1)) is True
    assert db.scalar(select(func.count()).select_from(User)) == 3
    assert db.scalar(select(func.count()).select_from(BlacklistNumber)) > 0
    assert db.scalar(select(func.count()).select_from(Report)) > 0
    assert db.scalar(select(func.count()).select_from(CallLog)) > 500
    assert seed_demo(db) is False  # รันซ้ำไม่สร้างซ้ำ
    assert db.scalar(select(func.count()).select_from(ScamCategory)) == 8

    from app.core.config import settings
    monkeypatch.setattr(settings, "SEED_DEMO_DATA", False)
    seed_main()  # ไม่ error และไม่สร้างข้อมูลเพิ่ม
