"""API + integration tests: detect / report / blacklist (Week 5-6 relations)"""
import httpx
import pytest
from sqlalchemy import func, select

from app.models import BlacklistNumber, CallLog, Report, report_categories


def _report(client, headers, phone="0812345678", score=90, **kw):
    body = {"phone_number": phone, "risk_score": score, **kw}
    return client.post("/api/report", headers=headers, json=body)


def test_detect_unknown_number_is_safe_and_logged(client, db):
    r = client.post("/api/detect/number", json={"phone_number": "081-111-2222"})
    assert r.status_code == 200
    data = r.json()
    assert data == {"phone_number": "0811112222", "status": "safe", "status_label": "ปลอดภัย",
                    "risk_score": 0, "report_count": 0, "is_blacklisted": False}
    log = db.scalar(select(CallLog))
    assert log.phone_number == "0811112222" and log.source.value == "number_check" and log.user_id is None


def test_detect_invalid_number(client):
    r = client.post("/api/detect/number", json={"phone_number": "12345"})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == "phone_number"


def test_report_requires_login(client):
    assert _report(client, {}).status_code == 401


def test_report_creates_and_aggregates(client, db, user, user_headers):
    r = _report(client, user_headers, phone="081-234-5678", score=60, note="  โทรมาหลอก  ",
                category_codes=["impersonate_police", "voice_clone", "voice_clone"])
    assert r.status_code == 201
    rep = r.json()["report"]
    assert rep["phone_number"] == "0812345678" and rep["note"] == "โทรมาหลอก"
    assert rep["reporter_username"] == "officer"
    assert [c["code"] for c in rep["categories"]] == ["impersonate_police", "voice_clone"]

    _report(client, user_headers, phone="0812345678", score=85)
    _report(client, user_headers, phone="0812345678", score=70)

    record = db.scalar(select(BlacklistNumber).where(BlacklistNumber.phone_number == "0812345678"))
    assert record.report_count == 3
    assert record.risk_score == 85 and record.status.value == "high_risk"
    assert db.scalar(select(func.count()).select_from(Report)) == 3

    d = client.post("/api/detect/number", json={"phone_number": "0812345678"}).json()
    assert d["is_blacklisted"] is True and d["report_count"] == 3


def test_report_unknown_category(client, user_headers):
    r = _report(client, user_headers, category_codes=["nope"])
    assert r.status_code == 400
    assert r.json()["error"]["details"] == {"unknown_codes": ["nope"]}


def test_report_validation(client, user_headers):
    assert _report(client, user_headers, score=101).status_code == 422
    assert _report(client, user_headers, note="x" * 1001).status_code == 422
    assert _report(client, user_headers, category_codes=["a", "b", "c", "d", "e", "f"]).status_code == 422


def test_categories_list(client):
    r = client.get("/api/categories")
    assert r.status_code == 200 and len(r.json()) == 8


def test_my_reports(client, user_headers, admin_headers):
    _report(client, user_headers, phone="0811111111")
    _report(client, user_headers, phone="0822222222", category_codes=["loan"])
    _report(client, admin_headers, phone="0833333333")
    r = client.get("/api/reports/me?page_size=1", headers=user_headers)
    data = r.json()
    assert data["total"] == 2 and len(data["items"]) == 1
    assert data["items"][0]["phone_number"] == "0822222222"  # ใหม่สุดก่อน


@pytest.fixture
def seeded_blacklist(db):
    rows = [("0811000001", 95), ("0811000002", 60), ("0822000003", 85), ("0811000004", 30), ("0899000005", 85)]
    from app.models.blacklist_number import status_from_score
    for phone, score in rows:
        db.add(BlacklistNumber(phone_number=phone, risk_score=score, report_count=1, status=status_from_score(score)))
    db.commit()


def test_blacklist_list_sorted_filtered_paginated(client, seeded_blacklist):
    data = client.get("/api/blacklist").json()
    assert data["total"] == 5
    scores = [i["risk_score"] for i in data["items"]]
    assert scores == sorted(scores, reverse=True)

    hi = client.get("/api/blacklist?status=high_risk").json()
    assert hi["total"] == 3 and all(i["status"] == "high_risk" for i in hi["items"])

    page2 = client.get("/api/blacklist?page=2&page_size=2").json()
    assert len(page2["items"]) == 2 and page2["page"] == 2

    search = client.get("/api/blacklist?q=0811").json()
    assert search["total"] == 3 and all(i["phone_number"].startswith("0811") for i in search["items"])
    assert client.get("/api/blacklist?q=08%25").status_code == 400  # wildcard ถูกปฏิเสธ
    assert client.get("/api/blacklist?page_size=1000").status_code == 422


def test_blacklist_detail(client, user_headers):
    _report(client, user_headers, phone="0812345678", category_codes=["parcel"])
    r = client.get("/api/blacklist/081-234-5678", headers=user_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["phone_number"] == "0812345678" and len(data["reports"]) == 1
    assert data["reports"][0]["categories"][0]["code"] == "parcel"
    assert client.get("/api/blacklist/0899999999", headers=user_headers).status_code == 404
    assert client.get("/api/blacklist/abc", headers=user_headers).status_code == 400


def test_blacklist_admin_crud(client, db, user_headers, admin_headers):
    body = {"phone_number": "0861234567", "risk_score": 88}
    assert client.post("/api/blacklist", headers=user_headers, json=body).status_code == 403
    r = client.post("/api/blacklist", headers=admin_headers, json=body)
    assert r.status_code == 201 and r.json()["status"] == "high_risk"
    assert client.post("/api/blacklist", headers=admin_headers, json=body).status_code == 409

    r = client.put("/api/blacklist/0861234567", headers=admin_headers, json={"risk_score": 55})
    assert r.json()["status"] == "suspect"
    r = client.put("/api/blacklist/0861234567", headers=admin_headers, json={"status": "safe"})
    assert r.json()["status"] == "safe" and r.json()["risk_score"] == 55
    assert client.put("/api/blacklist/0861234567", headers=admin_headers, json={}).status_code == 400
    assert client.put("/api/blacklist/0800000000", headers=admin_headers, json={"risk_score": 1}).status_code == 404

    # ลบเบอร์ -> report ถูกลบตาม (ON DELETE CASCADE) รวมถึงแถวใน report_categories
    _report(client, user_headers, phone="0861234567", category_codes=["loan"])
    assert client.delete("/api/blacklist/0861234567", headers=admin_headers).status_code == 200
    assert db.scalar(select(func.count()).select_from(Report)) == 0
    assert db.scalar(select(func.count()).select_from(report_categories)) == 0
    assert client.delete("/api/blacklist/0861234567", headers=admin_headers).status_code == 404


def test_detect_audio_falls_back_to_mock(client, db, user_headers):
    files = {"file": ("call.wav", b"RIFF....WAVEfmt ", "audio/wav")}
    r = client.post("/api/detect/audio?phone_number=0812345678", headers=user_headers, files=files)
    assert r.status_code == 200
    data = r.json()
    assert data["is_mock"] is True and data["risk_score"] == 87
    log = db.scalar(select(CallLog))
    assert log.source.value == "audio" and log.status.value == "high_risk"


def test_detect_audio_uses_ai_service(client, user_headers, monkeypatch):
    async def fake_post(self, url, files):
        return httpx.Response(200, json={"risk_score": 12, "is_synthetic_voice": False, "detail": {"ok": 1}},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    r = client.post("/api/detect/audio", headers=user_headers,
                    files={"file": ("a.mp3", b"ID3data", "audio/mpeg")})
    assert r.status_code == 200
    assert r.json()["risk_score"] == 12 and r.json()["is_mock"] is False


def test_detect_audio_rejects_bad_input(client, user_headers, monkeypatch):
    r = client.post("/api/detect/audio", headers=user_headers, files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400
    r = client.post("/api/detect/audio", headers=user_headers, files={"file": ("x.wav", b"", "audio/wav")})
    assert r.status_code == 400
    from app.core.config import settings
    monkeypatch.setattr(settings, "MAX_AUDIO_BYTES", 10)
    r = client.post("/api/detect/audio", headers=user_headers, files={"file": ("x.wav", b"0" * 11, "audio/wav")})
    assert r.status_code == 413
    assert client.post("/api/detect/audio", files={"file": ("x.wav", b"1", "audio/wav")}).status_code == 401
