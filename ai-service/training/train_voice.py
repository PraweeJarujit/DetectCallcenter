"""
เทรนโมเดล "เสียงจริง vs เสียงสังเคราะห์ (AI / deepfake)" จาก data/voice/manifest.csv

ขั้นตอน
  1. อ่านเสียงด้วยฟังก์ชันเดียวกับตอนใช้งานจริง (app.audio.load_audio) แล้วสุ่มตัดช่วง 4 วินาที
  2. ทุกคลิปได้ 2 ตัวอย่าง: เสียงเดิม 1 + เสียงที่ผ่าน augmentation (noise / สายโทรศัพท์ / ห้องก้อง) 1
  3. แบ่ง train/test แบบไม่ให้รั่ว: In-the-Wild แยกตาม "ผู้พูด", ภาษาไทยใช้ split "test" ของ FLEURS
     (ผู้พูดและประโยคใน test ไม่เคยถูกเห็นตอนเทรน เสียงปลอมไทยตามประโยคที่ใช้สร้าง)
  4. เทียบ 2 โมเดล (Logistic Regression, HistGradientBoosting) เลือกตัวที่ AUC ดีกว่า
  5. รายงานผลแยกตามแหล่งข้อมูล + แยกเฉพาะเสียงที่ผ่านสายโทรศัพท์ แล้วเทรนใหม่ด้วยข้อมูลทั้งหมด

รัน:  python -m training.train_voice --manifest data/voice/manifest.csv --out models
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.audio import SEGMENT_SECONDS, TARGET_SR, AudioDecodeError, load_audio, trim_silence  # noqa: E402
from app.features import N_FEATURES, extract_features, feature_names  # noqa: E402
from training.augment import phone_channel, random_augment  # noqa: E402

MODEL_VERSION = "voice-v2"


def _crop(x: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    win = int(SEGMENT_SECONDS * TARGET_SR)
    if len(x) <= win:
        return x
    start = int(rng.integers(0, len(x) - win))
    return x[start:start + win]


def _process(args: tuple[int, str]) -> tuple[int, np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """คืน (index, features เสียงเดิม, features เสียง augment, features เสียงผ่านสายโทรศัพท์)"""
    idx, path = args
    rng = np.random.default_rng(1000 + idx)
    try:
        audio = trim_silence(load_audio(Path(path).read_bytes()))
    except (AudioDecodeError, OSError, ValueError):
        return idx, None, None, None
    clean = _crop(audio, rng)
    aug, _ = random_augment(_crop(audio, rng), rng)
    phone = phone_channel(clean, rng)
    phone = phone / (np.max(np.abs(phone)) + 1e-9) * 0.95
    return idx, extract_features(clean), extract_features(aug), extract_features(phone)


def eer(y, prob) -> float:
    fpr, tpr, _ = roc_curve(y, prob)
    fnr = 1 - tpr
    i = int(np.nanargmin(np.abs(fnr - fpr)))
    return float((fpr[i] + fnr[i]) / 2)


def report(y, prob, threshold=0.5) -> dict:
    y = np.asarray(y)
    pred = (prob >= threshold).astype(int)
    out = {"n": int(len(y)), "accuracy": round(float(accuracy_score(y, pred)), 4)}
    if len(set(y.tolist())) == 2:
        tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
        out.update({
            "roc_auc": round(float(roc_auc_score(y, prob)), 4), "eer": round(eer(y, prob), 4),
            "real_correct_rate": round(tn / max(tn + fp, 1), 4), "fake_caught_rate": round(tp / max(tp + fn, 1), 4),
        })
    return out


def make_models() -> dict:
    return {
        "logreg": make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=4000, class_weight="balanced")),
        "hgb": HistGradientBoostingClassifier(max_iter=500, learning_rate=0.06, max_leaf_nodes=31,
                                              l2_regularization=1.0, class_weight="balanced",
                                              early_stopping=True, validation_fraction=0.1, random_state=0),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/voice/manifest.csv")
    ap.add_argument("--out", default=str(ROOT / "models"))
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--test-size", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.manifest, encoding="utf-8")))
    print(f"manifest rows: {len(rows)}")
    t0 = time.time()
    feats = np.zeros((len(rows), 3, N_FEATURES), dtype=np.float32)
    ok = np.zeros(len(rows), dtype=bool)
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for done, (i, f_clean, f_aug, f_phone) in enumerate(ex.map(_process, enumerate(r["path"] for r in rows), chunksize=16)):
            if f_clean is not None:
                feats[i] = (f_clean, f_aug, f_phone)
                ok[i] = True
            if done % 1000 == 0:
                print(f"  features {done}/{len(rows)}  {time.time() - t0:.0f}s")
    rows = [r for r, k in zip(rows, ok) if k]
    feats = feats[ok]
    feature_seconds = round(time.time() - t0, 1)
    print(f"usable clips: {len(rows)} (features {feature_seconds}s)")

    y = np.array([int(r["label"]) for r in rows])
    groups = np.array([r["group"] for r in rows])
    sources = np.array([r["source"] for r in rows])
    engines = np.array([r["engine"] for r in rows])

    # แบ่งแยกกันต่อแหล่ง เพื่อให้ทั้ง 2 แหล่งมีใน test เสมอ
    test_mask = np.zeros(len(rows), dtype=bool)
    splits = np.array([r.get("split") or "" for r in rows])
    for src in np.unique(sources):
        idx = np.where(sources == src)[0]
        if (splits[idx] == "test").any():  # FLEURS: ผู้พูด/ประโยคแยกกันอยู่แล้ว
            test_mask[idx[splits[idx] == "test"]] = True
            continue
        gss = GroupShuffleSplit(n_splits=1, test_size=args.test_size, random_state=args.seed)
        _, te = next(gss.split(idx, y[idx], groups[idx]))
        test_mask[idx[te]] = True
    tr_idx, te_idx = np.where(~test_mask)[0], np.where(test_mask)[0]

    def stack(idx, views=(0, 1)):
        X = np.concatenate([feats[idx, v] for v in views])
        return X, np.concatenate([y[idx]] * len(views))

    X_tr, y_tr = stack(tr_idx)
    X_te_clean, y_te = feats[te_idx, 0], y[te_idx]
    X_te_phone = feats[te_idx, 2]

    candidates = {}
    for name, model in make_models().items():
        t = time.time()
        model.fit(X_tr, y_tr)
        prob = model.predict_proba(X_te_clean)[:, 1]
        candidates[name] = {"model": model, "auc": roc_auc_score(y_te, prob), "fit_seconds": round(time.time() - t, 1)}
        print(f"  {name}: test AUC={candidates[name]['auc']:.4f}")
    best_name = max(candidates, key=lambda k: candidates[k]["auc"])
    best = candidates[best_name]["model"]

    prob_clean = best.predict_proba(X_te_clean)[:, 1]
    prob_phone = best.predict_proba(X_te_phone)[:, 1]
    evaluation = {
        "overall_clean": report(y_te, prob_clean),
        "overall_phone_channel": report(y_te, prob_phone),
        "by_source": {},
        "fake_caught_by_engine": {},
    }
    for src in np.unique(sources[te_idx]):
        m = sources[te_idx] == src
        evaluation["by_source"][str(src)] = {"clean": report(y_te[m], prob_clean[m]),
                                            "phone_channel": report(y_te[m], prob_phone[m])}
    for eng in np.unique(engines[te_idx]):
        m = (engines[te_idx] == eng) & (y_te == 1)
        if m.any():
            evaluation["fake_caught_by_engine"][str(eng)] = round(float((prob_clean[m] >= 0.5).mean()), 4)

    # เทรนใหม่ด้วยข้อมูลทั้งหมด (ทั้ง 3 มุมมอง) แล้วบันทึก
    final = make_models()[best_name]
    X_all, y_all = stack(np.arange(len(rows)), views=(0, 1, 2))
    final.fit(X_all, y_all)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": final, "version": MODEL_VERSION, "algorithm": best_name, "threshold": 0.5,
                 "feature_names": feature_names(), "segment_seconds": SEGMENT_SECONDS},
                out / "voice_model.joblib", compress=3)

    counts = {}
    for src in np.unique(sources):
        m = sources == src
        counts[str(src)] = {"real": int(((y == 0) & m).sum()), "fake": int(((y == 1) & m).sum())}
    metrics = {
        "model_version": MODEL_VERSION,
        "algorithm": best_name,
        "candidates_test_auc": {k: round(float(v["auc"]), 4) for k, v in candidates.items()},
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "n_features": N_FEATURES,
        "clips": counts,
        "fake_engines": {str(e): int((engines == e).sum()) for e in np.unique(engines)},
        "split": "In-the-Wild แยกตามผู้พูด (test 20%) / ไทยใช้ FLEURS split test (ผู้พูดและประโยคที่ไม่เคยเห็น)",
        "test": evaluation,
        "feature_seconds": feature_seconds,
    }
    (out / "voice_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics["test"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
