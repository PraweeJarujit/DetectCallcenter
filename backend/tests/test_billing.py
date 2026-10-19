"""API tests: สมาชิก Premium (โหมดทดลอง), โควตาตรวจเบอร์ฟรี, ตรวจข้อความ, ติดต่อเรา, หน้า admin"""
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.models import CallLog, ContactMessage, Payment
from app.models.payment import PaymentStatus


def _subscribe(client, headers):
    co = client.post("/api/billing/checkout", headers=headers, json={"method": "promptpay"})
    assert co.status_code == 201, co.text
    return co.json(), client.post(f"/api/billing/checkout/{co.json()['payment_id']}/confirm", headers=headers)


def test_plans_public(client):
    plans = client.get("/api/billing/plans").json()
    assert [p["code"] for p in plans] == ["free", "premium"]
    assert plans[1]["price_baht"] == 59


def test_subscribe_flow_activates_premium(client, db, user, user_headers):
    me = client.get("/api/billing/me", headers=user_headers).json()
    assert me["plan"] == "free" and me["usage"]["free_daily_limit"] == 5

    checkout, confirmed = _subscribe(client, user_headers)
    assert checkout["amount_baht"] == 59 and checkout["is_test_mode"] is True and checkout["reference"].startswith("VG")
    assert confirmed.status_code == 200
    body = confirmed.json()
    assert body["is_premium"] is True and body["auto_renew"] is True

    # ยืนยันซ้ำไม่ได้
    again = client.post(f"/api/billing/checkout/{checkout['payment_id']}/confirm", headers=user_headers)
    assert again.status_code == 400

    # ต่ออายุอีกรอบ -> ต่อจากวันหมดอายุเดิม (ไม่ทับ)
    first_until = datetime.fromisoformat(body["premium_until"].replace("Z", "+00:00"))
    _, second = _subscribe(client, user_headers)
    second_until = datetime.fromisoformat(second.json()["premium_until"].replace("Z", "+00:00"))
    assert (second_until - first_until).days == settings.PREMIUM_PERIOD_DAYS

    history = client.get("/api/billing/payments", headers=user_headers).json()
    assert len(history) == 2 and all(p["status"] == "paid" for p in history)
    assert client.get("/api/me", headers=user_headers).json()["plan"] == "premium"

    cancel = client.post("/api/billing/cancel", headers=user_headers)
    assert cancel.status_code == 200 and cancel.json()["auto_renew"] is False and cancel.json()["is_premium"] is True
    assert client.post("/api/billing/cancel", headers=user_headers).status_code == 400


def test_checkout_reuses_pending_and_expires(client, db, user_headers):
    a = client.post("/api/billing/checkout", headers=user_headers, json={}).json()
    b = client.post("/api/billing/checkout", headers=user_headers, json={}).json()
    assert a["payment_id"] == b["payment_id"]
    c = client.post("/api/billing/checkout", headers=user_headers, json={"method": "card"}).json()
    assert c["payment_id"] != a["payment_id"]

    payment = db.scalar(select(Payment).where(Payment.provider_ref == c["reference"]))
    payment.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    r = client.post(f"/api/billing/checkout/{c['payment_id']}/confirm", headers=user_headers)
    assert r.status_code == 400 and "หมดอายุ" in r.json()["error"]["message"]
    db.expire_all()
    assert db.get(Payment, payment.id).status == PaymentStatus.expired


def test_confirm_other_users_payment_is_404(client, make_user, user_headers):
    from tests.conftest import auth_header
    other = auth_header(make_user("someone.else"))
    co = client.post("/api/billing/checkout", headers=user_headers, json={}).json()
    assert client.post(f"/api/billing/checkout/{co['payment_id']}/confirm", headers=other).status_code == 404


def test_confirm_disabled_outside_mock(client, user_headers, monkeypatch):
    co = client.post("/api/billing/checkout", headers=user_headers, json={}).json()
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "stripe")
    assert client.post(f"/api/billing/checkout/{co['payment_id']}/confirm", headers=user_headers).status_code == 403


def test_admin_cannot_checkout(client, admin_headers):
    assert client.post("/api/billing/checkout", headers=admin_headers, json={}).status_code == 400


def test_free_quota_for_member_then_premium_unlimited(client, user_headers):
    for i in range(5):
        r = client.post("/api/detect/number", headers=user_headers, json={"phone_number": f"081000000{i}"})
        assert r.status_code == 200 and r.json()["remaining_today"] == 4 - i
    r = client.post("/api/detect/number", headers=user_headers, json={"phone_number": "0810000009"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "QUOTA_EXCEEDED"

    _subscribe(client, user_headers)
    r = client.post("/api/detect/number", headers=user_headers, json={"phone_number": "0810000009"})
    assert r.status_code == 200 and r.json()["remaining_today"] is None


def test_free_quota_for_anonymous(client):
    for _ in range(5):
        assert client.post("/api/detect/number", json={"phone_number": "0811111111"}).status_code == 200
    assert client.post("/api/detect/number", json={"phone_number": "0811111111"}).status_code == 429


def test_detect_text(client, db, premium_user, premium_headers, monkeypatch):
    async def fake_post(self, url, json):
        assert url.endswith("/analyze-text")
        return httpx.Response(200, json={"scam_probability": 0.93, "risk_score": 93, "level": "high",
                                         "signals": [{"code": "link", "label": "มีลิงก์", "match": "<url>"}]},
                              request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    client.post("/api/contacts", headers=premium_headers, json={"name": "แม่", "phone_number": "0811112222"})
    r = client.post("/api/detect/text", headers=premium_headers,
                    json={"text": "บัญชีของคุณถูกระงับ กดลิงก์ด่วน", "phone_number": "0899998888"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["level_label"] == "น่าจะเป็นมิจฉาชีพ" and body["signals"][0]["code"] == "link"
    assert body["alerted_contacts"] == ["แม่"]
    log = db.scalar(select(CallLog))
    assert log.source.value == "text" and log.phone_number == "0899998888"


def test_detect_text_requires_premium_and_valid_text(client, user_headers, premium_headers):
    assert client.post("/api/detect/text", headers=user_headers, json={"text": "hello"}).status_code == 402
    assert client.post("/api/detect/text", headers=premium_headers, json={"text": "   "}).status_code == 422
    assert client.post("/api/detect/text", headers=premium_headers, json={"text": "ทดสอบ"}).status_code == 503


def test_detect_text_mock_fallback(client, premium_headers, monkeypatch):
    monkeypatch.setattr(settings, "AI_MOCK_FALLBACK", True)
    r = client.post("/api/detect/text", headers=premium_headers, json={"text": "ทดสอบข้อความ"})
    assert r.status_code == 200 and r.json()["is_mock"] is True


def test_ai_status_unavailable(client):
    assert client.get("/api/ai/status").json() == {"available": False}


def test_ai_status_available(client, monkeypatch):
    async def fake_get(self, url):
        return httpx.Response(200, json={"status": "ok", "voice_model": True}, request=httpx.Request("GET", url))
    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)
    assert client.get("/api/ai/status").json()["available"] is True


def test_my_summary(client, user_headers):
    client.post("/api/detect/number", headers=user_headers, json={"phone_number": "0811111111"})
    s = client.get("/api/me/summary", headers=user_headers).json()
    assert s["checks_today"] == 1 and s["checks_total"] == 1 and s["reports_sent"] == 0


def test_contact_form_and_admin_inbox(client, db, admin_headers, user_headers):
    body = {"name": "สมหญิง", "email": "s@example.com", "topic": "billing", "message": "อยากสอบถามเรื่องการยกเลิกสมาชิก"}
    assert client.post("/api/contact", json=body).status_code == 201
    assert client.post("/api/contact", json={**body, "message": "สั้น"}).status_code == 422
    assert client.post("/api/contact", json={**body, "topic": "x"}).status_code == 422

    assert client.get("/api/admin/contact-messages", headers=user_headers).status_code == 403
    inbox = client.get("/api/admin/contact-messages?status=new", headers=admin_headers).json()
    assert inbox["total"] == 1
    msg_id = inbox["items"][0]["id"]
    r = client.put(f"/api/admin/contact-messages/{msg_id}", headers=admin_headers, json={"status": "handled"})
    assert r.status_code == 200 and r.json()["handled_at"]
    assert client.get("/api/admin/contact-messages?status=new", headers=admin_headers).json()["total"] == 0
    r = client.put(f"/api/admin/contact-messages/{msg_id}", headers=admin_headers, json={"status": "new"})
    assert r.json()["handled_at"] is None
    assert client.put("/api/admin/contact-messages/00000000-0000-0000-0000-000000000000", headers=admin_headers,
                      json={"status": "handled"}).status_code == 404
    assert db.query(ContactMessage).count() == 1


def test_contact_rate_limit(client, monkeypatch):
    body = {"name": "a", "email": "a@example.com", "message": "ข้อความทดสอบยาวพอสมควร"}
    for _ in range(settings.CONTACT_MAX_PER_HOUR):
        assert client.post("/api/contact", json=body).status_code == 201
    assert client.post("/api/contact", json=body).status_code == 429


def test_admin_overview(client, user_headers, admin_headers):
    _subscribe(client, user_headers)
    o = client.get("/api/admin/overview", headers=admin_headers).json()
    assert o["members"] == 1 and o["premium_members"] == 1
    assert o["revenue_this_month_baht"] == 59 and o["paid_this_month"] == 1
