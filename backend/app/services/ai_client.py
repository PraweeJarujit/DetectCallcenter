"""
ตัวเชื่อมต่อบริการ AI (ai-service) — backend เรียกผ่านโมดูลนี้ที่เดียว (test แทนที่ได้ง่ายด้วย monkeypatch)

  analyze_audio(bytes)  -> POST {VOICEGUARD_AI_URL}/analyze
  analyze_text(str)     -> POST {VOICEGUARD_AI_URL}/analyze-text
  status()              -> GET  {VOICEGUARD_AI_URL}/health
"""
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestError, ServiceUnavailableError

logger = logging.getLogger("app.ai")

UNAVAILABLE = "ระบบ AI ไม่พร้อมใช้งานชั่วคราว กรุณาลองใหม่อีกครั้งในไม่กี่นาที"


def _mock_audio() -> dict:
    return {"risk_score": 87, "is_synthetic_voice": True, "is_mock": True,
            "detail": {"note": "ผลจำลอง (AI_MOCK_FALLBACK=true)", "synthetic_probability": 0.87, "level": "high",
                       "segments_analyzed": 1, "segments_flagged": 1, "segment_scores": [87], "warnings": []}}


def _mock_text(text: str) -> dict:
    return {"scam_probability": 0.5, "risk_score": 50, "level": "medium", "signals": [], "is_mock": True}


async def _post(path: str, **kwargs) -> dict:
    try:
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            resp = await client.post(f"{settings.VOICEGUARD_AI_URL}{path}", **kwargs)
    except httpx.HTTPError as exc:
        logger.warning("ai-service unreachable %s: %s", path, type(exc).__name__)
        raise ServiceUnavailableError(UNAVAILABLE) from None
    if resp.status_code == 422:
        # ไฟล์เสียงเปิดไม่ได้ / สั้นเกิน — เป็นความผิดพลาดของ input ไม่ใช่ระบบล่ม
        detail = resp.json().get("detail") if resp.headers.get("content-type", "").startswith("application/json") else None
        raise BadRequestError(detail if isinstance(detail, str) else "ไฟล์หรือข้อความนี้วิเคราะห์ไม่ได้")
    if resp.status_code >= 400:
        logger.warning("ai-service %s -> HTTP %s", path, resp.status_code)
        raise ServiceUnavailableError(UNAVAILABLE)
    return resp.json()


async def analyze_audio(data: bytes, filename: str, content_type: str | None) -> dict:
    try:
        return await _post("/analyze", files={"file": (filename, data, content_type or "application/octet-stream")})
    except ServiceUnavailableError:
        if settings.AI_MOCK_FALLBACK:
            return _mock_audio()
        raise


async def analyze_text(text: str) -> dict:
    try:
        return await _post("/analyze-text", json={"text": text})
    except ServiceUnavailableError:
        if settings.AI_MOCK_FALLBACK:
            return _mock_text(text)
        raise


async def status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.VOICEGUARD_AI_URL}/health")
            resp.raise_for_status()
            return {"available": True, **resp.json()}
    except (httpx.HTTPError, ValueError):
        return {"available": False}
