import shutil
import subprocess

import numpy as np
import pytest

from app.audio import AudioDecodeError, load_audio, segments, trim_silence
from app.features import N_FEATURES, extract_features
from app.text_signals import find_signals, normalize_text
from tests.conftest import tone, wav_bytes
from training.augment import phone_channel, random_augment


def test_features_fixed_length_and_finite():
    for secs in (0.6, 3.0, 9.0):
        v = extract_features(tone(secs))
        assert v.shape == (N_FEATURES,)
        assert np.isfinite(v).all()


def test_features_differ_for_noise():
    a = extract_features(tone(noise=0.0))
    b = extract_features(tone(noise=0.1))
    assert not np.allclose(a, b)


def test_load_audio_resamples_and_normalizes():
    x = tone(2.0, sr=44100)
    out = load_audio(wav_bytes(x, sr=44100))
    assert abs(len(out) - 32000) < 10
    assert np.isclose(np.max(np.abs(out)), 0.95, atol=1e-3)


@pytest.mark.parametrize("data,msg", [(b"", "ว่าง"), (b"not audio at all" * 10, "")])
def test_load_audio_rejects_bad_input(data, msg):
    with pytest.raises(AudioDecodeError):
        load_audio(data)


def test_load_audio_rejects_silence_and_short():
    import io

    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000, np.float32), 16000, format="WAV")
    with pytest.raises(AudioDecodeError):
        load_audio(buf.getvalue())
    with pytest.raises(AudioDecodeError):
        load_audio(wav_bytes(tone(0.2)))


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_load_audio_mp3_via_ffmpeg(tmp_path):
    wav = tmp_path / "a.wav"
    wav.write_bytes(wav_bytes(tone(2.0)))
    mp3 = tmp_path / "a.mp3"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), str(mp3)], check=True)
    assert len(load_audio(mp3.read_bytes())) > 16000


def test_segments_and_trim():
    x = np.r_[np.zeros(16000, np.float32), tone(10.0), np.zeros(16000, np.float32)]
    trimmed = trim_silence(x)
    assert len(trimmed) < len(x)
    parts = segments(trimmed)
    assert len(parts) >= 4 and all(len(p) == 64000 for p in parts)
    assert len(segments(tone(2.0))) == 1
    assert len(segments(tone(200.0), max_segments=10)) == 10


def test_augment_keeps_length():
    rng = np.random.default_rng(0)
    x = tone(3.0)
    assert len(phone_channel(x, rng)) == len(x)
    y, applied = random_augment(x, rng)
    assert len(y) == len(x) and applied


def test_text_normalize_and_signals():
    t = "ตำรวจแจ้ง บัญชีของคุณเกี่ยวกับการฟอกเงิน โอนเงิน 5,000 บาท ภายใน 2 ชั่วโมง https://x-verify.xyz/a"
    norm = normalize_text(t)
    assert "<url>" in norm and "<money>" in norm
    codes = {s["code"] for s in find_signals(t)}
    assert {"authority", "threat", "money_request", "link"} <= codes
    assert find_signals("เย็นนี้กินข้าวบ้านนะ") == []


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["voice_model"] and r.json()["text_model"]


def test_analyze_audio(client):
    r = client.post("/analyze", files={"file": ("a.wav", wav_bytes(tone(6.0)), "audio/wav")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert 0 <= body["risk_score"] <= 100
    assert body["detail"]["segments_analyzed"] >= 2
    assert isinstance(body["is_synthetic_voice"], bool)


def test_analyze_audio_bad_file(client):
    r = client.post("/analyze", files={"file": ("a.wav", b"xx", "audio/wav")})
    assert r.status_code == 422


def test_analyze_text(client):
    scam = client.post("/analyze-text", json={"text": "เจ้าหน้าที่ตำรวจแจ้งว่าบัญชีของคุณเกี่ยวข้องกับคดีฟอกเงิน ต้องโอนเงินเพื่อตรวจสอบภายใน 2 ชั่วโมง"})
    normal = client.post("/analyze-text", json={"text": "เย็นนี้กินหมูกระทะกันไหม เจอกันที่สยามหกโมงเย็น"})
    assert scam.status_code == normal.status_code == 200
    assert scam.json()["scam_probability"] > normal.json()["scam_probability"]
    assert scam.json()["signals"]
    assert client.post("/analyze-text", json={"text": "   "}).status_code == 422
