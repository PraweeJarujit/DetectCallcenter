"""API tests: dashboard (/calls/*) — สถิติวันนี้, แนวโน้ม 7 วัน, keyset pagination"""
from datetime import timedelta

from app.models import CallLog
from app.models._common import utcnow
from app.models.blacklist_number import status_from_score
from app.models.call_log import CallSource
from app.routers.calls import local_midnight_utc, local_today


def _log(db, score, when, user=None, phone="0812345678"):
    db.add(CallLog(phone_number=phone, risk_score=score, status=status_from_score(score),
                   source=CallSource.demo, created_at=when, user_id=user.id if user else None))


def test_dashboard_requires_login(client):
    for p in ("/api/calls/stats", "/api/calls/trend", "/api/calls/logs"):
        assert client.get(p).status_code == 401


def test_stats_counts_only_today(client, db, user_headers):
    start = local_midnight_utc(local_today())
    _log(db, 90, start + timedelta(minutes=1))
    _log(db, 85, start + timedelta(minutes=2))
    _log(db, 20, start + timedelta(minutes=3))
    _log(db, 95, start - timedelta(minutes=1))   # เมื่อวาน (ตามเวลาไทย) ไม่นับ
    db.commit()
    data = client.get("/api/calls/stats", headers=user_headers).json()
    assert data["checked_today"] == 3
    assert data["high_risk_today"] == 2
    assert data["blocked_damage_baht"] == 2 * 35000
    assert data["model_accuracy"] > 0


def test_trend_has_7_days_and_counts_high_risk_only(client, db, user_headers):
    today_start = local_midnight_utc(local_today())
    _log(db, 90, today_start + timedelta(hours=1))
    _log(db, 81, today_start + timedelta(hours=2))
    _log(db, 50, today_start + timedelta(hours=3))                 # ไม่ใช่เสี่ยงสูง
    _log(db, 99, today_start - timedelta(days=2) + timedelta(hours=5))
    _log(db, 99, today_start - timedelta(days=9))                   # เก่ากว่า 7 วัน
    db.commit()
    trend = client.get("/api/calls/trend", headers=user_headers).json()
    assert len(trend) == 7
    assert trend[-1]["date"] == local_today().isoformat() and trend[-1]["risky_calls"] == 2
    assert trend[-3]["risky_calls"] == 1
    assert sum(p["risky_calls"] for p in trend) == 3
    assert all(p["day"] in ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."] for p in trend)


def test_logs_keyset_pagination(client, db, user, user_headers, admin_headers):
    now = utcnow()
    for i in range(5):
        _log(db, 10 * i, now - timedelta(minutes=i), user=user if i % 2 == 0 else None)
    db.commit()
    # admin เห็นทั้งระบบ (5 แถว)
    user_headers_all = admin_headers
    page1 = client.get("/api/calls/logs?limit=2", headers=user_headers_all).json()
    assert page1["total"] is None and len(page1["items"]) == 2
    assert page1["items"][0]["risk_score"] == 0  # ใหม่สุด
    page2 = client.get(f"/api/calls/logs?limit=2&before_id={page1['next_before_id']}", headers=user_headers_all).json()
    page3 = client.get(f"/api/calls/logs?limit=2&before_id={page2['next_before_id']}", headers=user_headers_all).json()
    seen = [i["id"] for p in (page1, page2, page3) for i in p["items"]]
    assert len(seen) == len(set(seen)) == 5
    assert page3["next_before_id"] is None

    mine = client.get("/api/calls/logs?mine=true", headers=user_headers).json()
    assert len(mine["items"]) == 3
    # สมาชิกทั่วไปขอดูทั้งระบบ -> ได้เฉพาะของตัวเองเสมอ
    assert len(client.get("/api/calls/logs", headers=user_headers).json()["items"]) == 3
    assert client.get("/api/calls/logs?before_id=999999", headers=user_headers).status_code == 404


def test_create_call_log_optional_auth(client, user_headers):
    r = client.post("/api/calls", json={"phone_number": "064-123-4521", "risk_score": 87, "is_synthetic_voice": True})
    assert r.status_code == 201
    assert r.json()["status"] == "high_risk" and r.json()["phone_number"] == "0641234521"
    r = client.post("/api/calls", headers=user_headers, json={"phone_number": "0641234521", "risk_score": 10})
    assert r.status_code == 201 and r.json()["status_label"] == "ปลอดภัย"
    assert client.post("/api/calls", json={"phone_number": "0641234521", "risk_score": -1}).status_code == 422


def test_demo_analysis_public(client):
    data = client.get("/api/calls/demo-analysis").json()
    assert data["risk_score"] == 87 and len(data["breakdown"]) == 4
