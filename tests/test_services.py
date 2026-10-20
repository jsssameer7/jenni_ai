import pytest
from pathlib import Path
from backend.config import settings
from backend.database import (
    init_db,
    save_memory,
    get_all_memories,
    delete_memory,
    is_sensitive_content
)
from backend.pc_control import pc_control_service
from backend.file_service import file_service
from backend.image_service import image_service
from backend.task_service import task_service

def setup_module():
    init_db()

def test_sensitive_content_detection():
    # Verify strict security filter
    assert is_sensitive_content("password = secret123") == True
    assert is_sensitive_content("my api_key is abcdef") == True
    assert is_sensitive_content("Bearer eyJhbGciOi...") == True
    assert is_sensitive_content("my name is Sameer") == False
    assert is_sensitive_content("I prefer dark mode in VS Code") == False

def test_memory_storage_and_sanitization():
    # Attempting to save a password must raise ValueError
    with pytest.raises(ValueError):
        save_memory("my_password", "supersecret123")

    # Storing standard preference works
    res = save_memory("theme_preference", "dark violet")
    assert res["status"] == "saved"
    assert res["key"] == "theme_preference"

    # Verify retrieval
    memories = get_all_memories()
    match = [m for m in memories if m["key"] == "theme_preference"]
    assert len(match) == 1
    assert match[0]["value"] == "dark violet"

    # Delete memory
    del_ok = delete_memory(match[0]["id"])
    assert del_ok == True

def test_pc_control_allowlist():
    # Approved apps
    calc_res = pc_control_service.open_app("calculator")
    assert "calc.exe" in str(calc_res) or calc_res["success"] == True

    # Dangerous / unapproved apps must be blocked
    bad_res = pc_control_service.open_app("format_c_drive")
    assert bad_res["success"] == False
    assert "not in the approved applications list" in bad_res["message"]

def test_file_service_path_traversal_protection():
    # Disallow path traversal to Windows System32
    bad_path = Path("C:/Windows/System32/cmd.exe")
    assert file_service.is_safe_path(bad_path) == False

    reveal_res = file_service.open_or_reveal_file(str(bad_path))
    assert reveal_res["success"] == False
    assert "Access denied" in reveal_res["message"]

def test_image_service_gpu_and_fallback():
    gpu = image_service.get_gpu_vram()
    assert "available" in gpu
    assert "recommendation" in gpu

    # Test creative art fallback generation
    filename = image_service.generate_creative_artwork("Futuristic Jarvis interface", width=200, height=100)
    assert filename.startswith("jenni_art_")
    assert (settings.IMAGES_PATH / filename).exists()

def test_task_workflows_listing():
    workflows = task_service.list_workflows()
    assert len(workflows) >= 3
    ids = [w["id"] for w in workflows]
    assert "wf_dev_setup" in ids
    assert "wf_daily_briefing" in ids
