import pytest
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

def test_memory_crud_api():
    # 1. Add preference
    post_res = client.post("/api/memory", json={"key": "favorite_editor", "value": "VS Code", "category": "preference"})
    assert post_res.status_code == 200
    assert post_res.json()["success"] == True

    # 2. Reject sensitive memory
    bad_res = client.post("/api/memory", json={"key": "api_key", "value": "sk-1234567890"})
    assert bad_res.status_code == 400

    # 3. List memories
    list_res = client.get("/api/memory")
    assert list_res.status_code == 200
    memories = list_res.json()
    target = next((m for m in memories if m["key"] == "favorite_editor"), None)
    assert target is not None

    # 4. Delete memory
    del_res = client.delete(f"/api/memory/{target['id']}")
    assert del_res.status_code == 200

def test_pc_control_api():
    # Get PC metrics
    status_res = client.get("/api/pc/status")
    assert status_res.status_code == 200
    data = status_res.json()
    assert "cpu_percent" in data
    assert "ram_percent" in data

    # Test approved app launch
    app_res = client.post("/api/pc/app", json={"app_name": "notepad"})
    assert app_res.status_code == 200
    assert app_res.json()["success"] == True

    # Test unapproved app launch blocked
    bad_app = client.post("/api/pc/app", json={"app_name": "malicious_script"})
    assert bad_app.status_code == 200
    assert bad_app.json()["success"] == False

def test_workflows_api():
    wf_res = client.get("/api/tasks/workflows")
    assert wf_res.status_code == 200
    workflows = wf_res.json()
    assert len(workflows) > 0

def test_mobile_info_api():
    info_res = client.get("/api/mobile/info")
    assert info_res.status_code == 200
    data = info_res.json()
    assert "tailscale_steps" in data
    assert "tasker_integration" in data

def test_frontend_serving():
    res = client.get("/")
    assert res.status_code == 200
    assert "Jenni AI" in res.text
    assert "Jenni AI — Your Personal Assistant" in res.text

    css_res = client.get("/static/styles.css")
    assert css_res.status_code == 200
    assert "--accent-cyan" in css_res.text

    js_res = client.get("/static/app.js")
    assert js_res.status_code == 200
    assert "setupNavigation" in js_res.text
