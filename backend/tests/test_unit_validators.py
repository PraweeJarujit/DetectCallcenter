"""Unit tests: validators / security / rate limiter / config (ไม่แตะ HTTP)"""
import pytest
from pydantic import ValidationError

from app.core import security
from app.core.config import Settings
from app.core.rate_limit import SlidingWindowLimiter
from app.core.validators import (
    normalize_phone,
    strip_text,
    validate_contact_phone,
    validate_password_strength,
    validate_phone_prefix,
    validate_thai_phone,
)
from app.database import normalize_db_url
from app.models.blacklist_number import NumberStatus, status_from_score


@pytest.mark.parametrize("raw,expected", [
    ("081-234-5678", "0812345678"),
    ("+66 81 234 5678", "0812345678"),
    ("66812345678", "0812345678"),
    ("(02) 123-4567", "021234567"),
    (" 0812345678 ", "0812345678"),
])
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected
    assert validate_thai_phone(raw) == expected


@pytest.mark.parametrize("bad", ["12", "1812345678", "08123", "08123456789", "abc", "081234567x"])
def test_invalid_thai_phone(bad):
    with pytest.raises(ValueError):
        validate_thai_phone(bad)


def test_contact_phone_accepts_hotline():
    assert validate_contact_phone("1441") == "1441"
    assert validate_contact_phone("081-555-1234") == "0815551234"
    with pytest.raises(ValueError):
        validate_contact_phone("999")


def test_phone_prefix():
    assert validate_phone_prefix("081-2") == "0812"
    for bad in ["%", "08_1", "abc", ""]:
        with pytest.raises(ValueError):
            validate_phone_prefix(bad)


def test_password_strength_and_strip():
    assert validate_password_strength("abc12345") == "abc12345"
    for bad in ["abcdefgh", "12345678"]:
        with pytest.raises(ValueError):
            validate_password_strength(bad)
    assert strip_text("  x ") == "x"
    assert strip_text("   ") is None
    assert strip_text(None) is None


@pytest.mark.parametrize("score,status", [
    (0, NumberStatus.safe), (49, NumberStatus.safe), (50, NumberStatus.suspect),
    (79, NumberStatus.suspect), (80, NumberStatus.high_risk), (100, NumberStatus.high_risk),
])
def test_status_from_score(score, status):
    assert status_from_score(score) == status


def test_password_hash_and_token_roundtrip():
    hashed = security.hash_password("Secret123")
    assert hashed != "Secret123"
    assert security.verify_password("Secret123", hashed)
    assert not security.verify_password("wrong", hashed)

    token = security.create_access_token("user-1", {"role": "gov"})
    payload = security.decode_access_token(token)
    assert payload["sub"] == "user-1" and payload["role"] == "gov" and payload["jti"]
    assert security.decode_access_token(token + "x") is None
    assert security.decode_access_token("not-a-jwt") is None


def test_rate_limiter():
    rl = SlidingWindowLimiter(max_attempts=2, window_seconds=60)
    assert not rl.is_blocked("k")
    rl.hit("k")
    rl.hit("k")
    assert rl.is_blocked("k")
    assert not rl.is_blocked("other")
    rl.reset("k")
    assert not rl.is_blocked("k")


def test_rate_limiter_window_expires(monkeypatch):
    import app.core.rate_limit as mod
    now = [1000.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
    rl = SlidingWindowLimiter(max_attempts=1, window_seconds=10)
    rl.hit("k")
    assert rl.is_blocked("k")
    now[0] += 11
    assert not rl.is_blocked("k")


def test_production_requires_strong_secret():
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="CHANGE_ME_IN_PRODUCTION")
    with pytest.raises(ValidationError):
        Settings(ENVIRONMENT="production", JWT_SECRET_KEY="x" * 40, CORS_ORIGINS="*")
    s = Settings(ENVIRONMENT=" Production ", JWT_SECRET_KEY="x" * 40, CORS_ORIGINS="https://a.com, https://b.com")
    assert s.ENVIRONMENT == "production"
    assert s.cors_origins == ["https://a.com", "https://b.com"]


def test_normalize_db_url():
    assert normalize_db_url("postgres://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_db_url("postgresql://u:p@h/db") == "postgresql+psycopg2://u:p@h/db"
    assert normalize_db_url("sqlite:///x.db") == "sqlite:///x.db"
