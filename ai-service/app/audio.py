"""
อ่านไฟล์เสียงทุกรูปแบบให้เป็น mono float32 ที่ 16 kHz และตัดเป็นช่วง ๆ สำหรับโมเดล

- wav / flac / ogg อ่านด้วย soundfile (เร็ว ไม่ต้องเรียกโปรแกรมภายนอก)
- mp3 / m4a / webm / aac (เช่นไฟล์เสียงจาก LINE หรือบันทึกจากมือถือ) แปลงด้วย ffmpeg
"""
from __future__ import annotations

import io
import shutil
import subprocess

import numpy as np
from scipy.signal import resample_poly

TARGET_SR = 16_000
SEGMENT_SECONDS = 4.0
SEGMENT_HOP_SECONDS = 2.0
MAX_SECONDS = 120.0
MIN_SECONDS = 0.5


class AudioDecodeError(ValueError):
    """ไฟล์เสียงเปิดไม่ได้หรือสั้นเกินไป"""


def _decode_soundfile(data: bytes) -> tuple[np.ndarray, int]:
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    return audio.mean(axis=1), int(sr)


def _decode_ffmpeg(data: bytes) -> tuple[np.ndarray, int]:
    if shutil.which("ffmpeg") is None:
        raise AudioDecodeError("เซิร์ฟเวอร์ไม่มี ffmpeg จึงเปิดไฟล์ประเภทนี้ไม่ได้ (ใช้ .wav แทน)")
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
         "-ac", "1", "-ar", str(TARGET_SR), "-f", "f32le", "pipe:1"],
        input=data, capture_output=True, timeout=60, check=False,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise AudioDecodeError("เปิดไฟล์เสียงไม่ได้ ไฟล์อาจเสียหรือไม่ใช่ไฟล์เสียง")
    return np.frombuffer(proc.stdout, dtype=np.float32).copy(), TARGET_SR


def resample(audio: np.ndarray, sr: int, target_sr: int = TARGET_SR) -> np.ndarray:
    if sr == target_sr:
        return audio.astype(np.float32, copy=False)
    g = np.gcd(int(sr), int(target_sr))
    return resample_poly(audio, target_sr // g, int(sr) // g).astype(np.float32)


def load_audio(data: bytes) -> np.ndarray:
    """bytes ของไฟล์เสียง -> numpy float32 mono 16 kHz (ยาวไม่เกิน MAX_SECONDS)"""
    if not data:
        raise AudioDecodeError("ไฟล์เสียงว่างเปล่า")
    try:
        audio, sr = _decode_soundfile(data)
    except Exception:  # noqa: BLE001 - soundfile เปิดไม่ได้ -> ลอง ffmpeg
        audio, sr = _decode_ffmpeg(data)
    audio = resample(audio, sr)
    audio = audio[: int(MAX_SECONDS * TARGET_SR)]
    audio = np.nan_to_num(audio)
    if len(audio) < MIN_SECONDS * TARGET_SR:
        raise AudioDecodeError(f"เสียงสั้นเกินไป ต้องยาวอย่างน้อย {MIN_SECONDS:g} วินาที")
    peak = float(np.max(np.abs(audio)))
    if peak < 1e-4:
        raise AudioDecodeError("ไฟล์นี้ไม่มีเสียงพูด (เงียบทั้งไฟล์)")
    return audio / peak * 0.95


def trim_silence(audio: np.ndarray, sr: int = TARGET_SR, threshold_db: float = -45.0) -> np.ndarray:
    """ตัดความเงียบหัว-ท้ายไฟล์ (เหลือขอบไว้ 0.1 วินาที)"""
    frame = int(0.02 * sr)
    if len(audio) < frame * 2:
        return audio
    n = len(audio) // frame
    energy = 10 * np.log10(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-10)
    loud = np.where(energy > threshold_db)[0]
    if len(loud) == 0:
        return audio
    pad = int(0.1 * sr)
    start = max(0, loud[0] * frame - pad)
    end = min(len(audio), (loud[-1] + 1) * frame + pad)
    return audio[start:end]


def segments(audio: np.ndarray, sr: int = TARGET_SR,
             seconds: float = SEGMENT_SECONDS, hop: float = SEGMENT_HOP_SECONDS,
             max_segments: int = 30) -> list[np.ndarray]:
    """ตัดเสียงยาวเป็นช่วงละ 4 วินาที ซ้อนกัน 2 วินาที (เสียงสั้นกว่านั้นได้ช่วงเดียว)"""
    win, step = int(seconds * sr), int(hop * sr)
    if len(audio) <= win:
        return [audio]
    out = [audio[i:i + win] for i in range(0, len(audio) - win + 1, step)]
    tail = len(audio) - win
    if tail % step:
        out.append(audio[tail:])
    if len(out) > max_segments:
        idx = np.linspace(0, len(out) - 1, max_segments).round().astype(int)
        out = [out[i] for i in idx]
    return out
