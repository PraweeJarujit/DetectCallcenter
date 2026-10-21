"""
เติมข้อมูลให้สายตัวอย่าง (frontend/audio/demo-calls.json) สำหรับหน้า "เดโมโทรศัพท์" (pages/demo.html)

  1. หาจังหวะเริ่ม-จบของแต่ละประโยคในไฟล์เสียงจริง ด้วย ffmpeg silencedetect
     (ไฟล์ทำโดย make_demo_calls.py ซึ่งเว้นช่วงหยุดพูด ~0.5-0.6 วินาทีระหว่างประโยค)
  2. ให้โมเดลข้อความจริง (models/text_model.joblib) ให้คะแนนคำพูดสะสมทีละประโยค
     แบบเดียวกับที่หน้าเว็บส่งคำพูดสะสมไปที่ POST /api/live/text ระหว่างสาย

ผลเก็บไว้ใน demo-calls.json -> lines: [{start, end, text, text_risk, signals}]
หน้าเดโมใช้ข้อมูลนี้เมื่อเรียก API สดไม่ได้ (เช่น server หลับ หรือโควตาหมด) ผลจึงยังเป็นผลจริงจากโมเดล ไม่ใช่ตัวเลขที่ตั้งเอง

รัน:  python -m training.annotate_demo_calls --audio ../frontend/audio
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.text_signals import find_signals  # noqa: E402


def speech_spans(mp3: Path, n_lines: int) -> list[tuple[float, float]]:
    """ช่วงที่มีเสียงพูด = ช่วงระหว่างความเงียบ เลือกเกณฑ์ที่แบ่งได้ตรงจำนวนประโยค"""
    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp3)],
        capture_output=True, text=True, check=True).stdout.strip())
    best = None
    for noise_db in (-38, -35, -32, -30, -42, -28, -45):
        for min_gap in (0.4, 0.35, 0.3, 0.45, 0.25):
            log = subprocess.run(
                ["ffmpeg", "-hide_banner", "-i", str(mp3), "-af", f"silencedetect=noise={noise_db}dB:d={min_gap}",
                 "-f", "null", "-"], capture_output=True, text=True).stderr
            starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
            ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
            silences = list(zip(starts, ends + [duration] * (len(starts) - len(ends))))
            spans, cursor = [], 0.0
            for s, e in silences:
                if s - cursor > 0.8:  # สั้นกว่านี้ไม่ใช่ประโยค
                    spans.append((round(cursor, 2), round(s, 2)))
                cursor = e
            if duration - cursor > 0.8:
                spans.append((round(cursor, 2), round(duration, 2)))
            if len(spans) == n_lines:
                return spans
            if best is None or abs(len(spans) - n_lines) < abs(len(best) - n_lines):
                best = spans
    # แบ่งไม่ลงตัว: ใช้สัดส่วนความยาวข้อความแทน (แบบเดียวกับคำบรรยายในหน้า ตรวจระหว่างสาย)
    print(f"  ! {mp3.name}: silencedetect ได้ {len(best or [])} ช่วง ไม่ตรง {n_lines} ประโยค ใช้สัดส่วนความยาวแทน")
    return []


def proportional_spans(lines: list[str], duration: float) -> list[tuple[float, float]]:
    total = sum(len(t) for t in lines) or 1
    out, t = [], 0.0
    for line in lines:
        d = len(line) / total * duration
        out.append((round(t, 2), round(t + d, 2)))
        t += d
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", default=str(ROOT.parent / "frontend" / "audio"))
    ap.add_argument("--models", default=str(ROOT / "models"))
    args = ap.parse_args()
    audio_dir = Path(args.audio)
    path = audio_dir / "demo-calls.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    model = joblib.load(Path(args.models) / "text_model.joblib")
    metrics = Path(args.models) / "text_metrics.json"
    if metrics.exists():
        m = json.loads(metrics.read_text(encoding="utf-8"))
        data["text_model"] = {"name": m.get("model"), "trained_at": m.get("trained_at")}

    for key, call in data.items():
        if not isinstance(call, dict) or "script" not in call:
            continue
        script = call["script"]
        spans = speech_spans(audio_dir / f"{key}.mp3", len(script)) or proportional_spans(script, call["seconds"])
        lines, said = [], ""
        for text, (start, end) in zip(script, spans):
            said = (said + " " + text).strip()
            prob = float(model.predict_proba([said[-1500:]])[0, 1])
            lines.append({
                "start": start, "end": end, "text": text,
                "text_risk": int(round(prob * 100)),
                "signals": [{"code": s["code"], "label": s["label"], "match": s["match"]} for s in find_signals(said)],
            })
        call["lines"] = lines
        print(key, [(ln["start"], ln["end"], ln["text_risk"], len(ln["signals"])) for ln in lines])

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
