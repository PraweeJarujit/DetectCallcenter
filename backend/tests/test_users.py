"""API tests: user management + authorization rules"""
import uuid

from tests.conftest import auth_header


def test_check_username(client, user):
    assert client.get("/api/check-username/officer").json()["available"] is False
    assert client.get("/api/check-username/free.name").json()["available"] is True
    assert client.get("/api/check-username/a").status_code == 422


def test_list_users_admin_only(client, user_headers, admin_headers, make_user):
    for i in range(3):
        make_user(f"u{i}")
    assert client.get("/api/users", headers=user_headers).status_code == 403
    r = client.get("/api/users?page=1&page_size=2", headers=admin_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 5 and len(data["items"]) == 2


def test_get_user_permissions(client, user, admin, user_headers, admin_headers):
    assert client.get(f"/api/users/{user.id}", headers=user_headers).status_code == 200
    assert client.get(f"/api/users/{admin.id}", headers=user_headers).status_code == 403
    assert client.get(f"/api/users/{user.id}", headers=admin_headers).status_code == 200
    assert client.get(f"/api/users/{uuid.uuid4()}", headers=admin_headers).status_code == 404


def test_update_self(client, user, user_headers):
    r = client.put(f"/api/users/{user.id}", headers=user_headers,
                   json={"full_name": "ชื่อใหม่", "auto_notify": False})
    assert r.status_code == 200
    assert r.json()["full_name"] == "ชื่อใหม่" and r.json()["auto_notify"] is False


def test_non_admin_cannot_change_role_or_others(client, user, admin, user_headers):
    assert client.put(f"/api/users/{user.id}", headers=user_headers, json={"role": "admin"}).status_code == 403
    assert client.put(f"/api/users/{admin.id}", headers=user_headers, json={"full_name": "x"}).status_code == 403
    assert client.put(f"/api/users/{user.id}", headers=user_headers, json={"unknown": 1}).status_code == 422


def test_admin_updates_user(client, user, admin, admin_headers):
    r = client.put(f"/api/users/{user.id}", headers=admin_headers,
                   json={"role": "telco", "is_active": False, "password": "Another123"})
    assert r.status_code == 200
    assert r.json()["role"] == "telco" and r.json()["is_active"] is False
    r = client.put(f"/api/users/{admin.id}", headers=admin_headers, json={"is_active": False})
    assert r.status_code == 400


def test_update_email_conflict(client, user, admin, user_headers):
    r = client.put(f"/api/users/{user.id}", headers=user_headers, json={"email": admin.email})
    assert r.status_code == 409


def test_delete_user(client, make_user, admin, admin_headers, user_headers):
    victim = make_user("victim")
    assert client.delete(f"/api/users/{victim.id}", headers=user_headers).status_code == 403
    assert client.delete(f"/api/users/{admin.id}", headers=admin_headers).status_code == 400
    assert client.delete(f"/api/users/{victim.id}", headers=admin_headers).status_code == 200
    assert client.delete(f"/api/users/{victim.id}", headers=admin_headers).status_code == 404
    assert client.get("/api/me", headers=auth_header(victim)).status_code == 401
