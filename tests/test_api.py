import pytest
import uuid
from fastapi.testclient import TestClient
from backend.main import app
from backend.config import settings

client = TestClient(app)

def test_api_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jenni AI"
    assert "qwen2.5:3b" in str(data)
    assert "greeting" in data

def test_auth_and_protected_flow():
    # 1. Unauthenticated request to protected route is rejected
    unauth = client.get("/api/memory")
    assert unauth.status_code == 401

    # 2. Login as admin (seeded default user)
    login_res = client.post("/api/auth/login", json={"username": "admin", "password": "jenni123"})
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "token" in login_data
    token = login_data["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Access /api/auth/me
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["username"] == "admin"

    # 4. Memory CRUD
    key = f"fav_lang_{uuid.uuid4().hex[:6]}"
    post_res = client.post("/api/memory", json={"key": key, "value": "Python 3.15", "category": "preference"}, headers=headers)
    assert post_res.status_code == 200
    assert post_res.json()["success"] is True

    list_res = client.get("/api/memory", headers=headers)
    assert list_res.status_code == 200
    memories = list_res.json()
    target = next((m for m in memories if m["key"] == key), None)
    assert target is not None

    del_res = client.delete(f"/api/memory/{target['id']}", headers=headers)
    assert del_res.status_code == 200

    # 5. PC control with token
    status_res = client.get("/api/pc/status", headers=headers)
    assert status_res.status_code == 200
    pc_data = status_res.json()
    assert "cpu_percent" in pc_data
    assert "ram_percent" in pc_data

    # Approved app launch
    app_res = client.post("/api/pc/app", json={"app_name": "notepad"}, headers=headers)
    assert app_res.status_code == 200
    assert app_res.json()["success"] is True

    # Approved website open
    web_res = client.post("/api/pc/website", json={"url": "https://google.com"}, headers=headers)
    assert web_res.status_code == 200
    assert web_res.json()["success"] is True

def test_frontend_serving():
    res = client.get("/")
    assert res.status_code == 200
    assert "Jenni AI" in res.text

    login_res = client.get("/login")
    assert login_res.status_code == 200
    assert "Sign In" in login_res.text

    app_res = client.get("/app")
    assert app_res.status_code == 200
    assert "Jenni AI" in app_res.text
