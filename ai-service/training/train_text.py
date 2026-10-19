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


WISESIGHT_RAW = "https://raw.githubusercontent.com/PyThaiNLP/wisesight-sentiment/master/kaggle-competition/train.txt"


def load_wisesight_texts(seed: int) -> list[str]:
    """ข้อความโซเชียลภาษาไทยจริง (wisesight_sentiment, CC0) — ลอง Hugging Face ก่อน ถ้าไม่ได้ใช้ไฟล์บน GitHub"""
    try:
        from datasets import load_dataset

        raw = load_dataset("pythainlp/wisesight_sentiment", split="train")["texts"]
    except Exception as e:  # noqa: BLE001
        import requests

        print(f"Hugging Face unavailable ({e.__class__.__name__}), using GitHub copy")
        resp = requests.get(WISESIGHT_RAW, timeout=60)
        resp.raise_for_status()
        raw = resp.text.splitlines()
    texts = [t.strip() for t in raw if t and 8 <= len(t.strip()) <= 400]
    random.Random(seed).shuffle(texts)
    return texts


def wisesight_rows(texts: list[str]) -> list[dict]:
    return [{"text": t, "label": 0, "category": "wisesight", "group": f"wisesight/{i // 100}"}
            for i, t in enumerate(texts)]


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
    ap.add_argument("--wisesight-weight", type=float, default=0.3,
                    help="น้ำหนักของข้อความ wisesight ต่อข้อความจากแม่แบบ (ข้อความโซเชียลมีเยอะ ถ้าน้ำหนักเท่ากันจะกลบสัญญาณหลอกลวง)")
    ap.add_argument("--no-wisesight", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rows = generate(per_template=args.per_template, seed=args.seed)
    sources = {"template_corpus": len(rows)}
    unseen_social: list[str] = []
    if not args.no_wisesight:
        ws_texts = load_wisesight_texts(args.seed)
        rows += wisesight_rows(ws_texts[: args.wisesight])
        # ข้อความโซเชียลที่ไม่ได้ใช้เทรนเลย ใช้วัดว่าโมเดลเตือนผิดกับข้อความทั่วไปบ่อยแค่ไหน
        unseen_social = ws_texts[args.wisesight: args.wisesight + 3000]
        sources["wisesight_sentiment"] = args.wisesight
    texts = [r["text"] for r in rows]
    y = np.array([r["label"] for r in rows])
    groups = np.array([r["group"] for r in rows])
    cats = np.array([r["category"] for r in rows])
    weights = np.where(cats == "wisesight", args.wisesight_weight, 1.0)
    print(f"rows={len(rows)} scam={int(y.sum())} normal={int((1 - y).sum())}")

    # 1) วัดผลแบบ "ไม่เคยเห็นแม่แบบนี้มาก่อน" (group split)
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=args.seed)
    tr, te = next(splitter.split(texts, y, groups))
    model = build_model()
    model.fit([texts[i] for i in tr], y[tr], clf__sample_weight=weights[tr])
    prob = model.predict_proba([texts[i] for i in te])[:, 1]
    held_out = scores(y[te], prob)
    per_category = {}
    for c in sorted(set(cats[te])):
        m = cats[te] == c
        per_category[c] = {"n": int(m.sum()), "correct_rate": round(float(((prob[m] >= 0.5) == y[te][m]).mean()), 4)}

    # 2) เทรนใหม่ด้วยข้อมูลทั้งหมด แล้ววัดกับชุดที่เขียนด้วยมือ (ไม่เคยถูกใช้เทรน)
    final = build_model()
    t0 = time.time()
    final.fit(texts, y, clf__sample_weight=weights)
    train_seconds = round(time.time() - t0, 1)
    eval_rows = [json.loads(line) for line in EVAL_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    eval_prob = final.predict_proba([r["text"] for r in eval_rows])[:, 1]
    hand_written = scores([r["label"] for r in eval_rows], eval_prob)
    social_false_alarm = None
    if unseen_social:
        sp = final.predict_proba(unseen_social)[:, 1]
        social_false_alarm = {"n": len(unseen_social), "flagged_rate": round(float((sp >= 0.5).mean()), 4),
                              "flagged_medium_or_high_rate": round(float((sp >= 0.4).mean()), 4)}
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
        "social_false_alarm": social_false_alarm,
        "wisesight_weight": None if args.no_wisesight else args.wisesight_weight,
        "hand_written_mistakes": mistakes,
        "threshold": 0.5,
    }
    (out / "text_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: metrics[k] for k in ("held_out_unseen_templates", "hand_written_eval", "social_false_alarm")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
