"""
test ไม่ต้องใช้ dataset จริง: สร้างโมเดลขนาดเล็กชั่วคราวใน tmp dir แล้วชี้ MODEL_DIR ไปที่นั่น
(โมเดลจริงอยู่ใน ai-service/models สร้างโดย GitHub Actions workflow "Train AI models")
"""
import io
import os
import tempfile
from pathlib import Path

import joblib
import numpy as np
import pytest
import soundfile as sf

_tmp = Path(tempfile.mkdtemp(prefix="vg-models-"))
os.environ["MODEL_DIR"] = str(_tmp)

from sklearn.linear_model import LogisticRegression  # noqa: E402

from app.features import N_FEATURES, extract_features, feature_names  # noqa: E402
from training.thai_scam_corpus import generate  # noqa: E402
from training.train_text import build_model  # noqa: E402


def tone(seconds=3.0, sr=16000, noise=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    x = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in range(1, 15)) * (np.sin(2 * np.pi * 2 * t) > -0.4)
    return (x + rng.normal(0, noise, len(t))).astype(np.float32)


def wav_bytes(x, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, x / np.max(np.abs(x)) * 0.8, sr, format="WAV")
    return buf.getvalue()


def _build_models():
    rows = generate(per_template=4, seed=1)
    m = build_model()
    m.fit([r["text"] for r in rows], [r["label"] for r in rows])
    joblib.dump(m, _tmp / "text_model.joblib")
    X = np.stack([extract_features(tone(noise=0.05 if i % 2 == 0 else 0.0, seed=i)) for i in range(12)])
    y = np.array([0 if i % 2 == 0 else 1 for i in range(12)])
    clf = LogisticRegression(max_iter=2000).fit(X, y)
    joblib.dump({"model": clf, "version": "test", "threshold": 0.5, "feature_names": feature_names()},
                _tmp / "voice_model.joblib")
    assert X.shape[1] == N_FEATURES


_build_models()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    return TestClient(app)
