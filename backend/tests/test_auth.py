"""API tests: /register /login /logout /change-password"""
from tests.conftest import PASSWORD, auth_header


def _register(client, **over):
    body = {"username": "new.user", "email": "new@example.com", "password": "Strong123"}
    body.update(over)
    return client.post("/api/register", json=body)


def test_register_success(client):
    r = _register(client, full_name="  สมชาย  ")
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "new.user"
    assert data["role"] == "member" and data["role_label"] == "สมาชิก"
    assert data["plan"] == "free" and data["is_premium"] is False
    assert data["full_name"] == "สมชาย"
    assert "hashed_password" not in data


def test_register_duplicate_username_and_email(client):
    assert _register(client).status_code == 201
    r = _register(client, email="other@example.com")
    assert r.status_code == 409 and "Username" in r.json()["error"]["message"]
    r = _register(client, username="another")
    assert r.status_code == 409 and "อีเมล" in r.json()["error"]["message"]


def test_register_validation_errors(client):
    r = _register(client, password="onlyletters")
    assert r.status_code == 422
    body = r.json()
    assert body["success"] is False and body["error"]["code"] == "VALIDATION_ERROR"
    assert body["error"]["details"][0]["field"] == "password"

    assert _register(client, role="admin").status_code == 422      # สมัครเป็น admin เองไม่ได้
    assert _register(client, username="bad name!").status_code == 422
    assert _register(client, email="not-an-email").status_code == 422


def test_login_success_and_me(client, user):
    r = client.post("/api/login", json={"username": "officer", "password": PASSWORD})
    assert r.status_code == 200
    data = r.json()
    assert data["token_type"] == "bearer" and data["expires_in"] > 0
    me = client.get("/api/me", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert me.status_code == 200 and me.json()["username"] == "officer"


def test_login_wrong_password_same_message_as_unknown_user(client, user):
    r1 = client.post("/api/login", json={"username": "officer", "password": "wrong"})
    r2 = client.post("/api/login", json={"username": "ghost", "password": "wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["message"] == r2.json()["error"]["message"]


def test_login_inactive_user(client, make_user):
    make_user("sleepy", is_active=False)
    r = client.post("/api/login", json={"username": "sleepy", "password": PASSWORD})
    assert r.status_code == 403


def test_login_rate_limited(client, user):
    for _ in range(3):  # LOGIN_MAX_ATTEMPTS=3 ใน conftest
        assert client.post("/api/login", json={"username": "officer", "password": "x"}).status_code == 401
    r = client.post("/api/login", json={"username": "officer", "password": PASSWORD})
    assert r.status_code == 429
    assert r.headers.get("Retry-After")


def test_protected_endpoint_requires_token(client):
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"
    assert client.get("/api/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_token_for_deleted_or_inactive_user_rejected(client, db, make_user):
    u = make_user("temp")
    headers = auth_header(u)
    u.is_active = False
    db.commit()
    assert client.get("/api/me", headers=headers).status_code == 401


def test_logout_revokes_token(client, user_headers):
    assert client.get("/api/me", headers=user_headers).status_code == 200
    r = client.post("/api/logout", headers=user_headers)
    assert r.status_code == 200
    assert client.post("/api/logout", headers=user_headers).status_code == 200  # logout ซ้ำได้
    r = client.get("/api/me", headers=user_headers)
    assert r.status_code == 401 and "ออกจากระบบ" in r.json()["error"]["message"]


def test_logout_without_token(client):
    assert client.post("/api/logout").status_code == 401


def test_change_password(client, user, user_headers):
    r = client.post("/api/change-password", headers=user_headers,
                    json={"old_password": "wrong", "new_password": "NewPass123"})
    assert r.status_code == 400
    r = client.post("/api/change-password", headers=user_headers,
                    json={"old_password": PASSWORD, "new_password": PASSWORD})
    assert r.status_code == 400
    r = client.post("/api/change-password", headers=user_headers,
                    json={"old_password": PASSWORD, "new_password": "NewPass123"})
    assert r.status_code == 200
    assert client.post("/api/login", json={"username": "officer", "password": "NewPass123"}).status_code == 200
