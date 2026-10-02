"""API tests: emergency contacts CRUD (Week 7-8 deliverable: frontend CRUD เต็มรูปแบบ)"""
from tests.conftest import auth_header


def test_contacts_crud(client, user_headers):
    assert client.get("/api/contacts", headers=user_headers).json() == []

    r = client.post("/api/contacts", headers=user_headers, json={"name": " แม่ ", "phone_number": "081-555-1234"})
    assert r.status_code == 201
    c = r.json()
    assert c["name"] == "แม่" and c["phone_number"] == "0815551234"

    r = client.post("/api/contacts", headers=user_headers, json={"name": "ตำรวจไซเบอร์", "phone_number": "1441"})
    assert r.status_code == 201
    assert len(client.get("/api/contacts", headers=user_headers).json()) == 2

    r = client.put(f"/api/contacts/{c['id']}", headers=user_headers, json={"name": "คุณแม่"})
    assert r.status_code == 200 and r.json()["name"] == "คุณแม่"
    assert client.put(f"/api/contacts/{c['id']}", headers=user_headers, json={}).status_code == 400

    assert client.delete(f"/api/contacts/{c['id']}", headers=user_headers).status_code == 200
    assert client.delete(f"/api/contacts/{c['id']}", headers=user_headers).status_code == 404
    assert len(client.get("/api/contacts", headers=user_headers).json()) == 1


def test_contacts_validation_and_duplicates(client, user_headers):
    assert client.post("/api/contacts", headers=user_headers, json={"name": "", "phone_number": "1441"}).status_code == 422
    assert client.post("/api/contacts", headers=user_headers, json={"name": "x", "phone_number": "999"}).status_code == 422
    client.post("/api/contacts", headers=user_headers, json={"name": "a", "phone_number": "0815551234"})
    r = client.post("/api/contacts", headers=user_headers, json={"name": "b", "phone_number": "081 555 1234"})
    assert r.status_code == 409
    other = client.post("/api/contacts", headers=user_headers, json={"name": "c", "phone_number": "0815550000"}).json()
    r = client.put(f"/api/contacts/{other['id']}", headers=user_headers, json={"phone_number": "0815551234"})
    assert r.status_code == 409


def test_contacts_limit(client, user_headers):
    for i in range(10):
        assert client.post("/api/contacts", headers=user_headers,
                           json={"name": f"p{i}", "phone_number": f"08155500{i:02d}"}).status_code == 201
    r = client.post("/api/contacts", headers=user_headers, json={"name": "x", "phone_number": "0815559999"})
    assert r.status_code == 400


def test_cannot_touch_other_users_contacts(client, make_user, user_headers):
    c = client.post("/api/contacts", headers=user_headers, json={"name": "a", "phone_number": "1441"}).json()
    intruder = auth_header(make_user("intruder"))
    assert client.get("/api/contacts", headers=intruder).json() == []
    assert client.put(f"/api/contacts/{c['id']}", headers=intruder, json={"name": "hack"}).status_code == 404
    assert client.delete(f"/api/contacts/{c['id']}", headers=intruder).status_code == 404


def test_contacts_deleted_with_user(client, db, make_user, admin_headers):
    victim = make_user("victim")
    client.post("/api/contacts", headers=auth_header(victim), json={"name": "a", "phone_number": "1441"})
    assert client.delete(f"/api/users/{victim.id}", headers=admin_headers).status_code == 200
    from sqlalchemy import func, select

    from app.models import EmergencyContact
    assert db.scalar(select(func.count()).select_from(EmergencyContact)) == 0
