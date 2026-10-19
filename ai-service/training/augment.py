"""
Data augmentation สำหรับโมเดลเสียง — ใช้กับ "ทั้งเสียงจริงและเสียงปลอม" ด้วยความน่าจะเป็นเท่ากัน

จุดประสงค์คือกันไม่ให้โมเดลเรียนทางลัด เช่น "เสียงสะอาด = ปลอม" (TTS ไม่มีเสียงรบกวน)
หรือ "ย่านความถี่สูงครบ = จริง" และให้ทนต่อเสียงที่ผ่านสายโทรศัพท์ (ตัดเหลือ 300-3400 Hz)
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, fftconvolve, resample_poly, sosfilt

SR = 16_000


def add_noise(x: np.ndarray, rng: np.random.Generator, snr_db: float) -> np.ndarray:
    noise = rng.standard_normal(len(x)).astype(np.float32)
    if rng.random() < 0.5:  # pink-ish noise (เหมือนเสียงพื้นหลังจริงมากกว่า white noise)
        noise = np.cumsum(noise)
        noise -= np.convolve(noise, np.ones(200) / 200, mode="same")
    sig_p = np.mean(x ** 2) + 1e-10
    noise_p = np.mean(noise ** 2) + 1e-10
    return x + noise * np.sqrt(sig_p / (noise_p * 10 ** (snr_db / 10)))


def phone_channel(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """จำลองสายโทรศัพท์: band-pass 300-3400 Hz, ลด sample rate เหลือ 8 kHz แล้วกลับ, μ-law 8 bit"""
    sos = butter(4, [300, 3400], btype="band", fs=SR, output="sos")
    y = sosfilt(sos, x)
    y = resample_poly(resample_poly(y, 1, 2), 2, 1)[: len(x)]
    if rng.random() < 0.6:
        mu = 255.0
        peak = np.max(np.abs(y)) + 1e-9
        c = np.sign(y / peak) * np.log1p(mu * np.abs(y / peak)) / np.log1p(mu)
        c = np.round(c * 127) / 127
        y = np.sign(c) * (np.expm1(np.abs(c) * np.log1p(mu)) / mu) * peak
    return y.astype(np.float32)


def reverb(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    rt = rng.uniform(0.15, 0.6)
    n = int(rt * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * np.exp(-6.9 * t / rt)
    ir[0] = 1.0
    ir /= np.sqrt(np.sum(ir ** 2))
    return fftconvolve(x, ir)[: len(x)].astype(np.float32)


def silence_gap(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """แทนช่วงหนึ่งด้วยความเงียบสนิทหรือเสียงรบกวนเบา ๆ (ทั้งเสียงจริงและปลอม) ให้โมเดลไม่ใช้ความเงียบเป็นตัวตัดสิน"""
    y = x.copy()
    n = int(rng.uniform(0.2, 0.9) * SR)
    if len(y) <= n * 2:
        return y
    start = int(rng.integers(0, len(y) - n))
    y[start:start + n] = 0.0 if rng.random() < 0.5 else rng.normal(0, 10 ** (rng.uniform(-4, -2.5)), n)
    return y


def random_augment(x: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, list[str]]:
    applied = []
    y = x.astype(np.float32)
    if rng.random() < 0.35:
        y = silence_gap(y, rng)
        applied.append("gap")
    if rng.random() < 0.3:
        y = reverb(y, rng)
        applied.append("reverb")
    if rng.random() < 0.5:
        y = phone_channel(y, rng)
        applied.append("phone")
    if rng.random() < 0.6:
        y = add_noise(y, rng, rng.uniform(10, 35))
        applied.append("noise")
    if applied in ([], ["gap"]):
        y = add_noise(y, rng, rng.uniform(20, 40))
        applied.append("noise")
    peak = np.max(np.abs(y)) + 1e-9
    # normalize เท่ากับตอนใช้งานจริง (app.audio.load_audio ปรับ peak เป็น 0.95 เสมอ)
    return (y / peak * 0.95).astype(np.float32), applied
