"""
เตรียมข้อมูลเสียงสำหรับเทรนโมเดล "เสียงจริง vs เสียงสังเคราะห์" -> data/voice/manifest.csv

แหล่งข้อมูล (ดาวน์โหลดอัตโนมัติจาก Hugging Face — รันบน GitHub Actions ได้):
  1. In-the-Wild (mueller91/In-The-Wild, CC BY-SA 4.0)
       เสียงจริงของบุคคลสาธารณะ 58 คน เทียบกับ deepfake ของคนเดียวกันที่เผยแพร่จริงบนอินเทอร์เน็ต
       (ภาษาอังกฤษ) — ใช้ meta.csv: file, speaker, label (bona-fide / spoof)
  2. FLEURS ภาษาไทย (google/fleurs th_th, CC BY 4.0) = เสียงคนไทยจริงอ่านประโยค
  3. เสียงสังเคราะห์ภาษาไทย สร้างจากประโยคเดียวกับข้อ 2 ด้วย TTS หลายเจ้า
       edge-tts (Microsoft Neural, 3 เสียง), gTTS (Google), MMS-TTS ไทย (Meta, ใช้ --with-mms)
     -> ประโยคเดียวกันทั้งเสียงจริงและปลอม ทำให้โมเดลต้องดูที่ "ลักษณะเสียง" ไม่ใช่ "เนื้อหา"

รัน:  python -m training.prepare_voice_data --out data/voice --itw-per-class 4000 --thai-fake 1500
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import random
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

import requests

HF = "https://huggingface.co/datasets"
ITW_URL = f"{HF}/mueller91/In-The-Wild/resolve/main/release_in_the_wild.zip"
FLEURS = f"{HF}/google/fleurs/resolve/main/data/th_th"
EDGE_VOICES = ["th-TH-PremwadeeNeural", "th-TH-NiwatNeural", "th-TH-AcharaNeural"]


def download(url: str, dest: Path, retries: int = 5) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            pos = tmp.stat().st_size if tmp.exists() else 0
            headers = {"Range": f"bytes={pos}-"} if pos else {}
            with requests.get(url, stream=True, timeout=60, headers=headers) as r:
                r.raise_for_status()
                mode = "ab" if pos and r.status_code == 206 else "wb"
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(1 << 20):
                        f.write(chunk)
            tmp.rename(dest)
            return dest
        except requests.RequestException as e:
            print(f"download retry {attempt + 1}: {e}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}")


def to_wav16k(src: Path, dst: Path) -> bool:
    proc = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
                          capture_output=True, check=False)
    return proc.returncode == 0 and dst.exists() and dst.stat().st_size > 1000


# ------------------------------ In-the-Wild ------------------------------

def prepare_itw(out: Path, zip_path: Path, per_class: int, rng: random.Random) -> list[dict]:
    if not zip_path.exists():
        download(ITW_URL, zip_path)
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        meta_name = next(n for n in names if n.lower().endswith("meta.csv"))
        prefix = meta_name[: -len("meta.csv")]
        meta = list(csv.DictReader(io.TextIOWrapper(zf.open(meta_name), encoding="utf-8")))
        keys = {k.lower().strip(): k for k in meta[0]}
        f_key, s_key, l_key = keys["file"], keys["speaker"], keys["label"]
        by_label: dict[int, list[dict]] = {0: [], 1: []}
        for m in meta:
            label = 0 if "bona" in m[l_key].lower() else 1
            by_label[label].append(m)
        target = out / "itw"
        target.mkdir(parents=True, exist_ok=True)
        for label, items in by_label.items():
            rng.shuffle(items)
            for m in items[:per_class]:
                member = prefix + m[f_key]
                dst = target / Path(m[f_key]).name
                if not dst.exists():
                    with zf.open(member) as src, open(dst, "wb") as f:
                        shutil.copyfileobj(src, f)
                rows.append({"path": str(dst), "label": label, "source": "itw",
                             "group": f"itw/{m[s_key]}", "engine": "real" if label == 0 else "deepfake"})
    print(f"In-the-Wild: {sum(r['label'] == 0 for r in rows)} real, {sum(r['label'] == 1 for r in rows)} fake")
    return rows


# ------------------------------ FLEURS Thai ------------------------------

def prepare_fleurs(out: Path, splits: list[str]) -> tuple[list[dict], dict[str, str]]:
    rows, sentences = [], {}
    target = out / "fleurs"
    target.mkdir(parents=True, exist_ok=True)
    for split in splits:
        tsv = download(f"{FLEURS}/{split}.tsv", out / "dl" / f"fleurs_{split}.tsv")
        tar = download(f"{FLEURS}/audio/{split}.tar.gz", out / "dl" / f"fleurs_{split}.tar.gz")
        meta = {}
        for line in tsv.read_text(encoding="utf-8").splitlines():
            cols = line.split("\t")
            if len(cols) >= 3:
                meta[cols[1]] = (cols[0], cols[2])
        with tarfile.open(tar) as tf:
            for member in tf:
                name = Path(member.name).name
                if not member.isfile() or name not in meta:
                    continue
                sid, text = meta[name]
                dst = target / name
                if not dst.exists():
                    with tf.extractfile(member) as src, open(dst, "wb") as f:
                        shutil.copyfileobj(src, f)
                sentences[sid] = text
                rows.append({"path": str(dst), "label": 0, "source": "thai", "group": f"th/{sid}", "engine": "fleurs"})
        tar.unlink(missing_ok=True)
    print(f"FLEURS th: {len(rows)} real clips, {len(sentences)} sentences")
    return rows, sentences


# ------------------------------ Thai TTS fakes ------------------------------

async def _edge_batch(jobs: list[tuple[str, str, Path]], rng: random.Random) -> None:
    import edge_tts

    sem = asyncio.Semaphore(4)

    async def one(sid, text, dst):
        async with sem:
            voice = rng.choice(EDGE_VOICES)
            rate = f"{rng.randint(-15, 15):+d}%"
            pitch = f"{rng.randint(-8, 8):+d}Hz"
            for attempt in range(3):
                try:
                    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(dst))
                    return
                except Exception as e:  # noqa: BLE001
                    print(f"edge-tts retry {sid}: {e}")
                    await asyncio.sleep(2 + attempt * 3)

    await asyncio.gather(*(one(*j) for j in jobs))


def make_fakes(out: Path, sentences: dict[str, str], n_total: int, with_mms: bool, rng: random.Random) -> list[dict]:
    target = out / "tts"
    target.mkdir(parents=True, exist_ok=True)
    sids = list(sentences)
    rng.shuffle(sids)
    engines = ["edge", "edge", "gtts"] + (["mms"] if with_mms else [])
    plan = [(sid, engines[i % len(engines)]) for i, sid in enumerate((sids * 3)[:n_total])]
    rows = []

    edge_jobs = [(sid, sentences[sid], target / f"edge_{i}_{sid}.mp3") for i, (sid, e) in enumerate(plan) if e == "edge"]
    try:
        asyncio.run(_edge_batch([j for j in edge_jobs if not j[2].exists()], rng))
    except Exception as e:  # noqa: BLE001
        print(f"edge-tts unavailable: {e}")

    gtts_jobs = [(i, sid) for i, (sid, e) in enumerate(plan) if e == "gtts"]
    try:
        from gtts import gTTS
        for i, sid in gtts_jobs:
            dst = target / f"gtts_{i}_{sid}.mp3"
            if dst.exists():
                continue
            try:
                gTTS(sentences[sid], lang="th", slow=rng.random() < 0.2).save(str(dst))
            except Exception as e:  # noqa: BLE001
                print(f"gTTS failed {sid}: {e}")
                time.sleep(3)
    except ImportError:
        print("gTTS not installed")

    mms_jobs = [(i, sid) for i, (sid, e) in enumerate(plan) if e == "mms"]
    if mms_jobs:
        try:
            import soundfile as sf
            import torch
            from transformers import AutoTokenizer, VitsModel
            tok = AutoTokenizer.from_pretrained("facebook/mms-tts-tha")
            model = VitsModel.from_pretrained("facebook/mms-tts-tha").eval()
            for i, sid in mms_jobs:
                dst = target / f"mms_{i}_{sid}.wav"
                if dst.exists():
                    continue
                inputs = tok(sentences[sid], return_tensors="pt")
                with torch.no_grad():
                    model.speaking_rate = rng.uniform(0.9, 1.15)
                    wav = model(**inputs).waveform[0].numpy()
                sf.write(dst, wav, model.config.sampling_rate)
        except Exception as e:  # noqa: BLE001
            print(f"MMS-TTS unavailable: {e}")

    for f in sorted(target.iterdir()):
        if f.suffix not in (".mp3", ".wav") or f.stem.endswith("_16k"):
            continue
        engine, _, sid = f.stem.split("_", 2)
        wav = f.with_name(f.stem + "_16k.wav")
        if not wav.exists() and not to_wav16k(f, wav):
            continue
        rows.append({"path": str(wav), "label": 1, "source": "thai", "group": f"th/{sid}", "engine": engine})
    counts = {e: sum(r["engine"] == e for r in rows) for e in ("edge", "gtts", "mms")}
    print(f"Thai TTS fakes: {len(rows)} {counts}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/voice")
    ap.add_argument("--itw-zip", default=None, help="ไฟล์ zip ที่ดาวน์โหลดไว้แล้ว (ถ้าไม่มีจะดาวน์โหลดเอง 8 GB)")
    ap.add_argument("--itw-per-class", type=int, default=4000)
    ap.add_argument("--fleurs-splits", default="dev,test")
    ap.add_argument("--thai-fake", type=int, default=1500)
    ap.add_argument("--with-mms", action="store_true")
    ap.add_argument("--skip-itw", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    if not args.skip_itw:
        zip_path = Path(args.itw_zip) if args.itw_zip else out / "dl" / "release_in_the_wild.zip"
        rows += prepare_itw(out, zip_path, args.itw_per_class, rng)
    real_th, sentences = prepare_fleurs(out, args.fleurs_splits.split(","))
    rows += real_th
    rows += make_fakes(out, sentences, args.thai_fake, args.with_mms, rng)

    with open(out / "manifest.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["path", "label", "source", "group", "engine"])
        w.writeheader()
        w.writerows(rows)
    print(f"manifest: {len(rows)} rows -> {out / 'manifest.csv'}")


if __name__ == "__main__":
    main()
