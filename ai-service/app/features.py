"""
สกัดคุณลักษณะ (features) จากเสียงสำหรับแยก "เสียงคนจริง" กับ "เสียงสังเคราะห์/AI"

ใช้แค่ numpy + scipy (ไม่ใช้ librosa/torch) เพื่อให้บริการเล็กพอรันบนเซิร์ฟเวอร์ RAM 512 MB

แนวคิด: เสียงจาก TTS / voice clone มักทิ้งร่องรอยไว้ที่
  - สเปกตรัมช่วงความถี่สูง (vocoder สร้างย่าน 4-8 kHz ได้ไม่เหมือนธรรมชาติ)  -> LFCC, LTAS, high-band ratio
  - ความเรียบของสเปกตรัมและการเปลี่ยนแปลงระหว่างเฟรม                      -> flatness, flux, deltas
ทุก feature คำนวณจากเฉพาะเฟรมที่มีเสียงพูด แล้วสรุปเป็นค่าเฉลี่ย / ส่วนเบี่ยงเบน / เปอร์เซ็นไทล์ ได้เวกเตอร์ยาวคงที่

ไม่ใช้ลักษณะของ "ช่วงเงียบ" (voice-v1 เคยใช้) เพราะโมเดลไปจำว่าเงียบสนิท = TTS แทนที่จะดูตัวเสียง
และแอปโทรศัพท์/LINE ก็ตัดเสียงรบกวนจนเงียบสนิทได้เหมือนกัน ทำให้เสียงคนจริงถูกตีว่าเป็น AI
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from scipy.fft import dct, rfft

from app.audio import TARGET_SR

N_FFT = 512
WIN = 400   # 25 ms
HOP = 160   # 10 ms
N_MEL = 40
N_LIN = 40
N_CEP = 20
N_LTAS = 32
EPS = 1e-10

SPECTRAL_NAMES = ["centroid", "bandwidth", "rolloff", "flatness", "zcr", "log_rms", "hf_ratio", "vhf_ratio", "flux"]


def _hz_to_mel(f):
    return 2595.0 * np.log10(1.0 + np.asarray(f) / 700.0)


def _mel_to_hz(m):
    return 700.0 * (10 ** (np.asarray(m) / 2595.0) - 1.0)


def _triangular_bank(edges_hz: np.ndarray, sr: int, n_fft: int) -> np.ndarray:
    bins = np.fft.rfftfreq(n_fft, 1.0 / sr)
    n = len(edges_hz) - 2
    bank = np.zeros((n, len(bins)), dtype=np.float32)
    for i in range(n):
        lo, mid, hi = edges_hz[i], edges_hz[i + 1], edges_hz[i + 2]
        up = (bins - lo) / max(mid - lo, EPS)
        down = (hi - bins) / max(hi - mid, EPS)
        bank[i] = np.clip(np.minimum(up, down), 0, None)
    return bank


@lru_cache(maxsize=4)
def mel_bank(sr: int = TARGET_SR) -> np.ndarray:
    edges = _mel_to_hz(np.linspace(_hz_to_mel(20), _hz_to_mel(sr / 2), N_MEL + 2))
    return _triangular_bank(edges, sr, N_FFT)


@lru_cache(maxsize=4)
def linear_bank(sr: int = TARGET_SR) -> np.ndarray:
    return _triangular_bank(np.linspace(0, sr / 2, N_LIN + 2), sr, N_FFT)


def frame_signal(audio: np.ndarray) -> np.ndarray:
    if len(audio) < WIN:
        audio = np.pad(audio, (0, WIN - len(audio)))
    n = 1 + (len(audio) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    return audio[idx]


def _deltas(x: np.ndarray) -> np.ndarray:
    """delta แบบ regression 2 เฟรม (เหมือนสูตรมาตรฐานของ HTK)"""
    if len(x) < 3:
        return np.zeros_like(x)
    padded = np.pad(x, ((2, 2), (0, 0)), mode="edge")
    return (padded[3:-1] - padded[1:-3] + 2 * (padded[4:] - padded[:-4])) / 10.0


def _stats(x: np.ndarray, percentiles: bool = False) -> np.ndarray:
    parts = [x.mean(axis=0), x.std(axis=0)]
    if percentiles:
        parts += [np.percentile(x, 10, axis=0), np.percentile(x, 90, axis=0)]
    return np.concatenate(parts)


def feature_names() -> list[str]:
    names: list[str] = []
    for block in ("mfcc", "d_mfcc", "lfcc", "d_lfcc"):
        for stat in ("mean", "std"):
            names += [f"{block}{i}_{stat}" for i in range(N_CEP)]
    for stat in ("mean", "std", "p10", "p90"):
        names += [f"{n}_{stat}" for n in SPECTRAL_NAMES]
    names += [f"ltas{i}" for i in range(N_LTAS)]
    return names


N_FEATURES = len(feature_names())


def extract_features(audio: np.ndarray, sr: int = TARGET_SR) -> np.ndarray:
    """เสียง mono 16 kHz -> เวกเตอร์ features ยาว N_FEATURES"""
    if sr != TARGET_SR:
        raise ValueError("audio must be 16 kHz")
    audio = audio.astype(np.float64)
    emphasized = np.append(audio[0], audio[1:] - 0.97 * audio[:-1])

    raw_frames = frame_signal(audio)
    frames = frame_signal(emphasized) * np.hanning(WIN)
    power = np.abs(rfft(frames, n=N_FFT, axis=1)) ** 2 / N_FFT  # (T, 257)

    frame_db = 10 * np.log10(np.mean(raw_frames ** 2, axis=1) + EPS)
    loud_threshold = frame_db.max() - 40.0
    voiced = frame_db > loud_threshold
    if voiced.sum() < 5:
        voiced = np.ones_like(voiced, dtype=bool)
    p = power[voiced]
    rf = raw_frames[voiced]

    log_mel = np.log(p @ mel_bank(sr).T + EPS)
    mfcc = dct(log_mel, type=2, axis=1, norm="ortho")[:, :N_CEP]
    log_lin = np.log(p @ linear_bank(sr).T + EPS)
    lfcc = dct(log_lin, type=2, axis=1, norm="ortho")[:, :N_CEP]

    freqs = np.fft.rfftfreq(N_FFT, 1.0 / sr)
    total = p.sum(axis=1) + EPS
    centroid = (p @ freqs) / total
    bandwidth = np.sqrt(np.abs((p @ freqs ** 2) / total - centroid ** 2))
    cumulative = np.cumsum(p, axis=1)
    rolloff = freqs[np.argmax(cumulative >= 0.85 * cumulative[:, -1:], axis=1)]
    flatness = np.exp(np.mean(np.log(p + EPS), axis=1)) / (np.mean(p, axis=1) + EPS)
    zcr = np.mean(np.abs(np.diff(np.sign(rf), axis=1)) > 0, axis=1)
    log_rms = 0.5 * np.log10(np.mean(rf ** 2, axis=1) + EPS)
    hf_ratio = p[:, freqs >= 4000].sum(axis=1) / total
    vhf_ratio = p[:, freqs >= 6000].sum(axis=1) / total
    norm_spec = p / total[:, None]
    flux = np.r_[0.0, np.sqrt(np.sum(np.diff(norm_spec, axis=0) ** 2, axis=1))]
    spectral = np.stack([centroid / 1000, bandwidth / 1000, rolloff / 1000, flatness, zcr,
                         log_rms, hf_ratio, vhf_ratio, flux], axis=1)

    # Long-term average spectrum: รูปร่างสเปกตรัมเฉลี่ยทั้งคลิป (normalize ด้วยพลังงานรวม)
    ltas_bands = np.array_split(np.arange(power.shape[1]), N_LTAS)
    mean_spec = p.mean(axis=0)
    ltas = np.log10(np.array([mean_spec[b].sum() for b in ltas_bands]) / (mean_spec.sum() + EPS) + EPS)


    vec = np.concatenate([
        _stats(mfcc), _stats(_deltas(mfcc)), _stats(lfcc), _stats(_deltas(lfcc)),
        _stats(spectral, percentiles=True), ltas,
    ]).astype(np.float32)
    return np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
