"""
สร้างไฟล์เสียง "สายตัวอย่าง" สำหรับหน้า ตรวจระหว่างสาย (frontend/audio/)

  scam_ai.mp3     มิจฉาชีพแอบอ้างเป็นตำรวจ พูดด้วยเสียงสังเคราะห์ (edge-tts) — ข้อความเขียนใหม่ ไม่อยู่ในชุดเทรน
  real_human.mp3  เสียงคนไทยจริงจาก FLEURS split "test" (ผู้พูดที่โมเดลไม่เคยได้ยินตอนเทรน) CC-BY 4.0

ทั้งสองไฟล์ผ่านช่องสัญญาณโทรศัพท์จำลองแบบเดียวกัน แล้วให้โมเดลจริงให้คะแนนทีละช่วง 4 วินาที (เลื่อนทีละ 2 วินาที
แบบเดียวกับหน้าเว็บ) เก็บผลไว้ใน demo-calls.json เพื่อตรวจว่าเดโมแสดงผลตามจริง

รัน:  python -m training.make_demo_calls --out ../frontend/audio
"""
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

import joblib
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.audio import TARGET_SR, load_audio  # noqa: E402
from app.features import extract_features  # noqa: E402
from training.augment import phone_channel  # noqa: E402
from training.prepare_voice_data import FLEURS, download  # noqa: E402

SCAM_SCRIPT = [
    "สวัสดีครับ ผมสิบตำรวจโทวิชัย จากกองบังคับการปราบปรามครับ",
    "ตอนนี้มีคนนำบัตรประชาชนของคุณไปเปิดบัญชีธนาคาร ใช้รับเงินจากแก๊งพนันออนไลน์",
    "บัญชีนี้มีเงินผิดกฎหมายผ่านเข้าออกหลายล้านบาท คุณตกเป็นผู้ต้องสงสัยในคดีฟอกเงินนะครับ",
    "ระหว่างนี้ห้ามวางสาย และห้ามเล่าเรื่องนี้ให้ใครฟังเด็ดขาด รวมถึงคนในครอบครัว",
    "เพื่อพิสูจน์ว่าคุณบริสุทธิ์ ต้องโอนเงินทั้งหมดในบัญชีมาให้เจ้าหน้าที่ตรวจสอบก่อน",
    "ถ้าตรวจแล้วไม่พบความผิด เราจะโอนคืนให้ภายในยี่สิบสี่ชั่วโมงครับ",
    "เดี๋ยวผมส่งเลขบัญชีของทางราชการให้ทางไลน์ กรุณาทำรายการภายในสามสิบนาทีนะครับ",
]
SCAM_VOICE = "th-TH-NiwatNeural"


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


_noise_rng = np.random.default_rng(11)


def _gap(seconds: float) -> np.ndarray:
    """ช่วงหยุดพูดแบบสายจริง: มีเสียงรบกวนเบา ๆ ของสาย ไม่ใช่เงียบสนิท (ใช้เหมือนกันทั้ง 2 ไฟล์)"""
    return _noise_rng.normal(0, 0.002, int(seconds * TARGET_SR)).astype(np.float32)


async def _tts(text: str, dst: Path) -> None:
    import edge_tts

    await edge_tts.Communicate(text, SCAM_VOICE, rate="-6%").save(str(dst))


def make_scam(tmp: Path) -> np.ndarray:
    parts = []
    for i, line in enumerate(SCAM_SCRIPT):
        mp3, wav = tmp / f"scam_{i}.mp3", tmp / f"scam_{i}.wav"
        asyncio.run(_tts(line, mp3))
        _ffmpeg("-i", str(mp3), "-ac", "1", "-ar", str(TARGET_SR), str(wav))
        audio, _ = sf.read(wav, dtype="float32")
        parts += [audio, _gap(0.6)]
    return np.concatenate(parts)


def make_real(tmp: Path, seconds: float = 34.0) -> tuple[np.ndarray, list[str]]:
    tsv = download(f"{FLEURS}/test.tsv", tmp / "test.tsv")
    tar = download(f"{FLEURS}/audio/test.tar.gz", tmp / "test.tar.gz")
    rows = [line.split("\t") for line in tsv.read_text(encoding="utf-8").splitlines()]
    # ใช้ผู้พูดเพศเดียวกันทั้งไฟล์ ให้ฟังเหมือนคนคนเดียวคุยโทรศัพท์
    wanted = {r[1]: r[2] for r in rows if len(r) >= 7 and r[6].strip().upper() == "FEMALE"}
    if len(wanted) < 10:  # ถ้ารูปแบบคอลัมน์เพศไม่ตรง ใช้ทุกไฟล์
        wanted = {r[1]: r[2] for r in rows if len(r) >= 3}
    parts, used, total = [], [], 0.0
    with tarfile.open(tar) as tf:
        for member in tf:
            name = Path(member.name).name
            if not member.isfile() or name not in wanted:
                continue
            src = tmp / name
            with tf.extractfile(member) as f:
                src.write_bytes(f.read())
            audio, sr = sf.read(src, dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            if sr != TARGET_SR:
                wav = tmp / f"{name}.16k.wav"
                _ffmpeg("-i", str(src), "-ac", "1", "-ar", str(TARGET_SR), str(wav))
                audio, _ = sf.read(wav, dtype="float32")
            dur = len(audio) / TARGET_SR
            if not 4.0 <= dur <= 12.0:
                continue
            parts += [audio, _gap(0.5)]
            used.append(wanted[name])
            total += dur + 0.5
            if total >= seconds:
                break
    return np.concatenate(parts), used


def finish(audio: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    y = phone_channel(audio, rng)
    return (y / (np.max(np.abs(y)) + 1e-9) * 0.9).astype(np.float32)


def score_windows(bundle: dict, wav_bytes: bytes) -> list[int]:
    """ให้คะแนนแบบเดียวกับหน้าเว็บ: หน้าต่าง 4 วินาที เลื่อนทีละ 2 วินาที"""
    audio, _ = sf.read(__import__("io").BytesIO(wav_bytes), dtype="float32")
    win, hop, out = 4 * TARGET_SR, 2 * TARGET_SR, []
    for start in range(0, max(1, len(audio) - win + 1), hop):
        chunk = audio[start:start + win]
        if np.sqrt(np.mean(chunk ** 2)) < 0.01:  # ช่วงเงียบ หน้าเว็บไม่ส่งไปตรวจ
            continue
        buf = __import__("io").BytesIO()
        sf.write(buf, chunk, TARGET_SR, format="WAV", subtype="PCM_16")
        x = extract_features(load_audio(buf.getvalue()))
        out.append(int(round(float(bundle["model"].predict_proba(x[None, :])[0, 1]) * 100)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "frontend" / "audio"))
    ap.add_argument("--models", default=str(ROOT / "models"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bundle = joblib.load(Path(args.models) / "voice_model.joblib")
    rng = np.random.default_rng(3)

    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        clips = {"scam_ai": (make_scam(tmp), {"script": SCAM_SCRIPT, "voice": f"edge-tts {SCAM_VOICE}"})}
        real, used = make_real(tmp)
        clips["real_human"] = (real, {"script": used, "voice": "FLEURS th_th test split (CC-BY 4.0), held out from training"})

        report = {"model_version": bundle.get("version")}
        for name, (audio, meta) in clips.items():
            audio = finish(audio, rng)
            wav = tmp / f"{name}.wav"
            sf.write(wav, audio, TARGET_SR, subtype="PCM_16")
            _ffmpeg("-i", str(wav), "-ac", "1", "-ar", "16000", "-b:a", "48k", str(out / f"{name}.mp3"))
            scores = score_windows(bundle, wav.read_bytes())
            report[name] = {"seconds": round(len(audio) / TARGET_SR, 1), "window_scores": scores,
                            "mean": round(float(np.mean(scores)), 1), **meta}
            print(name, report[name]["seconds"], "s, mean", report[name]["mean"], scores, flush=True)
    (out / "demo-calls.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
