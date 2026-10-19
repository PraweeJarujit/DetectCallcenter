"""
เทรนโมเดลจับข้อความหลอกลวงภาษาไทย (SMS / LINE / คำพูดที่ถอดจากสาย)

ข้อมูล:
  - ข้อความหลอกลวง + ข้อความปกติที่หน้าตาคล้าย (hard negatives) จาก thai_scam_corpus.py
  - ข้อความปกติจริงจาก pythainlp/wisesight_sentiment (Hugging Face, CC0) — ใส่ --no-wisesight เพื่อข้าม (ตอนไม่มีเน็ต)
  - ชุดทดสอบที่เขียนแยกด้วยมือ eval_texts_th.jsonl (ไม่ได้มาจากแม่แบบ) ใช้วัดว่าโมเดลใช้กับข้อความจริงได้แค่ไหน

โมเดล: TF-IDF ของ character n-gram (2-5 ตัวอักษร ไม่ต้องตัดคำภาษาไทย) + Logistic Regression
       ไฟล์โมเดลเล็ก (~ไม่กี่ MB) ทำนายได้ในเสี้ยววินาทีบน CPU

รัน:  python -m training.train_text --out models
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import joblib
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.text_signals import normalize_text  # noqa: E402
from training.thai_scam_corpus import generate  # noqa: E402

EVAL_FILE = Path(__file__).with_name("eval_texts_th.jsonl")


def load_wisesight(n: int, seed: int) -> list[dict]:
    from datasets import load_dataset

    ds = load_dataset("pythainlp/wisesight_sentiment", split="train")
    texts = [t.strip() for t in ds["texts"] if t and 8 <= len(t.strip()) <= 400]
    random.Random(seed).shuffle(texts)
    return [{"text": t, "label": 0, "category": "wisesight", "group": f"wisesight/{i // 100}"}
            for i, t in enumerate(texts[:n])]


def build_model() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(preprocessor=normalize_text, analyzer="char_wb", ngram_range=(2, 5),
                                  min_df=2, max_features=80_000, sublinear_tf=True)),
        ("clf", LogisticRegression(C=4.0, class_weight="balanced", max_iter=3000)),
    ])


def scores(y_true, prob, threshold=0.5) -> dict:
    pred = (np.asarray(prob) >= threshold).astype(int)
    out = {
        "n": int(len(y_true)), "accuracy": round(accuracy_score(y_true, pred), 4),
        "precision": round(precision_score(y_true, pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, pred, zero_division=0), 4),
        "f1": round(f1_score(y_true, pred, zero_division=0), 4),
    }
    if len(set(y_true)) == 2:
        out["roc_auc"] = round(roc_auc_score(y_true, prob), 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "models"))
    ap.add_argument("--per-template", type=int, default=40)
    ap.add_argument("--wisesight", type=int, default=6000, help="จำนวนข้อความปกติจาก wisesight")
    ap.add_argument("--no-wisesight", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = generate(per_template=args.per_template, seed=args.seed)
    sources = {"template_corpus": len(rows)}
    if not args.no_wisesight:
        ws = load_wisesight(args.wisesight, args.seed)
        rows += ws
        sources["wisesight_sentiment"] = len(ws)
    texts = [r["text"] for r in rows]
    y = np.array([r["label"] for r in rows])
    groups = np.array([r["group"] for r in rows])
    cats = np.array([r["category"] for r in rows])
    print(f"rows={len(rows)} scam={int(y.sum())} normal={int((1 - y).sum())}")

    # 1) วัดผลแบบ "ไม่เคยเห็นแม่แบบนี้มาก่อน" (group split)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=args.seed)
    tr, te = next(splitter.split(texts, y, groups))
    model = build_model()
    model.fit([texts[i] for i in tr], y[tr])
    prob = model.predict_proba([texts[i] for i in te])[:, 1]
    held_out = scores(y[te], prob)
    per_category = {}
    for c in sorted(set(cats[te])):
        m = cats[te] == c
        per_category[c] = {"n": int(m.sum()), "correct_rate": round(float(((prob[m] >= 0.5) == y[te][m]).mean()), 4)}

    # 2) เทรนใหม่ด้วยข้อมูลทั้งหมด แล้ววัดกับชุดที่เขียนด้วยมือ (ไม่เคยถูกใช้เทรน)
    final = build_model()
    t0 = time.time()
    final.fit(texts, y)
    train_seconds = round(time.time() - t0, 1)
    eval_rows = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    eval_prob = final.predict_proba([r["text"] for r in eval_rows])[:, 1]
    hand_written = scores([r["label"] for r in eval_rows], eval_prob)
    mistakes = [{"text": r["text"], "label": r["label"], "scam_probability": round(float(p), 3)}
                for r, p in zip(eval_rows, eval_prob) if (p >= 0.5) != bool(r["label"])]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(final, out / "text_model.joblib", compress=3)
    metrics = {
        "model": "char n-gram TF-IDF (2-5) + LogisticRegression",
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "train_seconds": train_seconds,
        "data_sources": sources,
        "n_train_total": len(rows),
        "held_out_unseen_templates": held_out,
        "held_out_per_category": per_category,
        "hand_written_eval": hand_written,
        "hand_written_mistakes": mistakes,
        "threshold": 0.5,
    }
    (out / "text_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("held_out_unseen_templates", "hand_written_eval")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
