"""ตรวจระหว่างสาย: โควตาทดลองฟรี, ส่งต่อให้ ai-service, สรุปผลตอนจบสาย"""
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.call_log import CallLog
from app.routers.live import live_quota, summary_limiter
from app.services import ai_client


@pytest.fixture(autouse=True)
def _reset_live_limits():
    live_quota.reset()
    summary_limiter.reset()
    yield


@pytest.fixture
def fake_ai(monkeypatch):
    calls = {"audio": 0, "text": []}

    async def analyze_audio(data, filename, content_type):
        calls["audio"] += 1
        return {"risk_score": 91, "is_synthetic_voice": True,
                "detail": {"synthetic_probability": 0.913, "processing_ms": 40}}

    async def analyze_text(text):
        calls["text"].append(text)
        return {"risk_score": 88, "level": "high", "scam_probability": 0.88,
                "signals": [{"code": "authority", "label": "อ้างเป็นเจ้าหน้าที่", "match": "ตำรวจ"}]}

    monkeypatch.setattr(ai_client, "analyze_audio", analyze_audio)
    monkeypatch.setattr(ai_client, "analyze_text", analyze_text)
    return calls


WAV = {"file": ("chunk.wav", b"RIFF" + b"\0" * 64, "audio/wav")}


def test_quota_for_each_plan(client, user_headers, premium_headers):
    anon = client.get("/api/live/quota").json()
    assert anon["premium"] is False and anon["free_chunks_left"] == settings.LIVE_FREE_CHUNKS_PER_DAY
    assert anon["free_seconds_left"] == settings.LIVE_FREE_CHUNKS_PER_DAY * 2 and anon["text_analysis"] is False
    assert client.get("/api/live/quota", headers=user_headers).json()["premium"] is False
    prem = client.get("/api/live/quota", headers=premium_headers).json()
    assert prem["premium"] is True and prem["free_chunks_left"] is None and prem["text_analysis"] is True


def test_chunk_uses_free_quota_then_blocks(client, fake_ai, monkeypatch):
    monkeypatch.setattr(live_quota, "max_attempts", 2)
    r = client.post("/api/live/chunk", files=WAV)
    assert r.status_code == 200
    body = r.json()
    assert body["risk_score"] == 91 and body["synthetic_probability"] == 0.913 and body["free_chunks_left"] == 1
    assert client.post("/api/live/chunk", files=WAV).json()["free_chunks_left"] == 0
    r = client.post("/api/live/chunk", files=WAV)
    assert r.status_code == 429 and r.json()["error"]["code"] == "QUOTA_EXCEEDED"
    assert fake_ai["audio"] == 2


def test_free_quota_is_per_account(client, fake_ai, user_headers, monkeypatch):
    monkeypatch.setattr(live_quota, "max_attempts", 1)
    assert client.post("/api/live/chunk", files=WAV, headers=user_headers).status_code == 200
    assert client.post("/api/live/chunk", files=WAV, headers=user_headers).status_code == 429
    assert client.post("/api/live/chunk", files=WAV).status_code == 200  # ไม่ login นับแยกตาม IP


def test_premium_chunks_are_unlimited(client, fake_ai, premium_headers, monkeypatch):
    monkeypatch.setattr(live_quota, "max_attempts", 1)
    for _ in range(3):
        r = client.post("/api/live/chunk", files=WAV, headers=premium_headers)
        assert r.status_code == 200 and r.json()["free_chunks_left"] is None


def test_chunk_rejects_empty_and_large(client, fake_ai, monkeypatch):
    assert client.post("/api/live/chunk", files={"file": ("c.wav", b"", "audio/wav")}).status_code == 400
    monkeypatch.setattr(settings, "LIVE_MAX_CHUNK_BYTES", 10)
    assert client.post("/api/live/chunk", files={"file": ("c.wav", b"0" * 11, "audio/wav")}).status_code == 413
    assert fake_ai["audio"] == 0


def test_chunk_when_ai_is_down_is_503_and_not_counted(client, monkeypatch):
    monkeypatch.setattr(settings, "VOICEGUARD_AI_URL", "http://127.0.0.1:9")
    r = client.post("/api/live/chunk", files=WAV)
    assert r.status_code == 503
    assert client.get("/api/live/quota").json()["free_chunks_left"] == settings.LIVE_FREE_CHUNKS_PER_DAY


def test_live_text_is_premium_and_not_logged(client, db, fake_ai, user_headers, premium_headers):
    payload = {"text": "สวัสดีครับ ผมเป็นตำรวจ บัญชีคุณมีปัญหา"}
    assert client.post("/api/live/text", json=payload, headers=user_headers).status_code == 402
    r = client.post("/api/live/text", json=payload, headers=premium_headers)
    assert r.status_code == 200
    assert r.json()["level"] == "high" and r.json()["signals"][0]["code"] == "authority"
    assert db.scalar(select(CallLog)) is None


def test_summary_logs_one_row_and_alerts_contacts(client, db, premium_user, premium_headers):
    r = client.post("/api/contacts", headers=premium_headers, json={"name": "คุณแม่", "phone_number": "0815551234"})
    assert r.status_code == 201
    r = client.post("/api/live/summary", headers=premium_headers, json={
        "phone_number": "081-234-5678", "duration_seconds": 42, "voice_risk": 86, "text_risk": 70,
        "chunks_analyzed": 20})
    assert r.status_code == 200
    body = r.json()
    assert body["risk_score"] == 86 and body["status"] == "high_risk" and body["is_synthetic_voice"] is True
    assert body["alerted_contacts"] == ["คุณแม่"]
    log = db.scalar(select(CallLog))
    assert log.source.value == "live" and log.user_id == premium_user.id and log.phone_number == "0812345678"
    assert client.get("/api/calls/logs", headers=premium_headers).json()["items"][0]["source"] == "live"


def test_summary_without_login_and_rate_limit(client, db, monkeypatch):
    payload = {"duration_seconds": 10, "voice_risk": 12, "chunks_analyzed": 4}
    r = client.post("/api/live/summary", json=payload)
    assert r.status_code == 200
    assert r.json()["status"] == "safe" and r.json()["alerted_contacts"] == [] and r.json()["is_synthetic_voice"] is False
    monkeypatch.setattr(summary_limiter, "max_attempts", 1)
    assert client.post("/api/live/summary", json=payload).status_code == 429
