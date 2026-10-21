"""
AwayCall AI service — บริการโมเดล AI แยกจาก backend หลัก

  POST /analyze        ไฟล์เสียง -> ความน่าจะเป็นที่เป็นเสียงสังเคราะห์ (AI / deepfake)
  POST /analyze-text   ข้อความ SMS / LINE / คำพูดในสาย -> ความน่าจะเป็นที่เป็นการหลอกลวง + สัญญาณเตือน
  GET  /health         สถานะ + เวอร์ชันโมเดล + ผลวัดความแม่นยำล่าสุด

backend (FastAPI หลัก) เป็นคนเรียกบริการนี้ ผู้ใช้ไม่ได้เรียกตรง
"""
from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.audio import TARGET_SR, AudioDecodeError, load_audio, segments, trim_silence
from app.features import extract_features
from app.text_signals import find_signals

logger = logging.getLogger("voiceguard-ai")
logging.basicConfig(level=logging.INFO)

MODEL_DIR = Path(os.getenv("MODEL_DIR", Path(__file__).resolve().parents[1] / "models"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))

app = FastAPI(title="AwayCall AI service", version="1.0.0")


@lru_cache(maxsize=1)
def voice_bundle() -> dict | None:
    path = MODEL_DIR / "voice_model.joblib"
    if not path.exists():
        logger.warning("voice model not found at %s", path)
        return None
    return joblib.load(path)


@lru_cache(maxsize=1)
def text_model():
    path = MODEL_DIR / "text_model.joblib"
    if not path.exists():
        logger.warning("text model not found at %s", path)
        return None
    return joblib.load(path)


def _metrics(name: str) -> dict | None:
    path = MODEL_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


@app.get("/health")
def health():
    voice_m, text_m = _metrics("voice_metrics.json") or {}, _metrics("text_metrics.json") or {}
    return {
        "status": "ok",
        "voice_model": voice_bundle() is not None,
        "text_model": text_model() is not None,
        "voice_model_version": (voice_bundle() or {}).get("version"),
        "voice_test": (voice_m.get("test") or {}).get("overall_clean"),
        "text_test": text_m.get("held_out_unseen_templates"),
    }


def verdict(prob: float) -> str:
    if prob >= 0.7:
        return "high"
    if prob >= 0.4:
        return "medium"
    return "low"


@app.post("/analyze")
async def analyze_audio(file: UploadFile = File(...)):
    bundle = voice_bundle()
    if bundle is None:
        raise HTTPException(503, "ยังไม่ได้ติดตั้งโมเดลเสียง")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "ไฟล์ใหญ่เกินกำหนด")
    t0 = time.time()
    try:
        audio = trim_silence(load_audio(data))
    except AudioDecodeError as e:
        raise HTTPException(422, str(e)) from None

    parts = segments(audio)
    X = np.stack([extract_features(p) for p in parts])
    probs = bundle["model"].predict_proba(X)[:, 1]
    # ค่าเฉลี่ยของช่วงที่คะแนนสูงครึ่งบน: ถ้าแค่บางช่วงของสายเป็นเสียง AI ก็ยังจับได้ แต่ไม่ไวเกินจาก 1 ช่วง
    top = np.sort(probs)[::-1][: max(1, int(np.ceil(len(probs) / 2)))]
    prob = float(top.mean())
    duration = len(audio) / TARGET_SR
    threshold = float(bundle.get("threshold", 0.5))
    warnings = []
    if duration < 2.0:
        warnings.append("เสียงสั้นกว่า 2 วินาที ผลอาจคลาดเคลื่อน ควรใช้คลิปยาว 5 วินาทีขึ้นไป")
    return {
        "risk_score": int(round(prob * 100)),
        "is_synthetic_voice": prob >= threshold,
        "detail": {
            "synthetic_probability": round(prob, 4),
            "level": verdict(prob),
            "duration_seconds": round(duration, 2),
            "segments_analyzed": len(parts),
            "segments_flagged": int((probs >= threshold).sum()),
            "segment_scores": [int(round(p * 100)) for p in probs],
            "model_version": bundle.get("version"),
            "processing_ms": int((time.time() - t0) * 1000),
            "warnings": warnings,
        },
    }


class TextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


@app.post("/analyze-text")
def analyze_text(payload: TextRequest):
    model = text_model()
    if model is None:
        raise HTTPException(503, "ยังไม่ได้ติดตั้งโมเดลข้อความ")
    text = payload.text.strip()
    if not text:
        raise HTTPException(422, "ข้อความว่างเปล่า")
    prob = float(model.predict_proba([text])[0, 1])
    signals = find_signals(text)
    level = verdict(prob)
    # สัญญาณเตือนหลายข้อพร้อมกันแต่โมเดลให้คะแนนต่ำ -> อย่างน้อยให้ "น่าสงสัย"
    if level == "low" and len(signals) >= 3:
        level = "medium"
    return {
        "scam_probability": round(prob, 4),
        "risk_score": int(round(prob * 100)),
        "level": level,
        "signals": signals,
    }
