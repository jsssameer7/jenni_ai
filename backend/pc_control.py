import subprocess
import webbrowser
import psutil
import uuid
import json
import re
import time
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from backend.config import settings
from backend.database import log_action
from backend.mongodb import get_sync_db

# Cache for installed Windows StartApps
_installed_apps_cache: List[Dict[str, str]] = []
_last_cache_time: float = 0.0

# Known common URI schemes and binary aliases for Windows 11
KNOWN_APP_LAUNCHERS: Dict[str, str] = {
    "whatsapp": "whatsapp:",
    "spotify": "spotify:",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "msedge": "msedge",
    "browser": "start",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "visual studio code": "code",
    "calc": "calc.exe",
    "calculator": "calc.exe",
    "notepad": "notepad.exe",
    "notes": "notepad.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "files": "explorer.exe",
    "my computer": "explorer.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "taskmgr": "taskmgr.exe",
    "settings": "ms-settings:",
    "windows settings": "ms-settings:",
    "camera": "microsoft.windows.camera:",
    "photos": "ms-photos:",
    "clock": "ms-clock:",
    "alarms": "ms-clock:",
    "discord": "discord:",
    "telegram": "tg:",
    "teams": "msteams:",
    "zoom": "zoommtg:",
    "word": "winword.exe",
    "ms word": "winword.exe",
    "microsoft word": "winword.exe",
    "excel": "excel.exe",
    "ms excel": "excel.exe",
    "powerpoint": "powerpnt.exe",
    "ppt": "powerpnt.exe",
    "android studio": "studio64.exe",
    "photoshop": "photoshop",
    "adobe photoshop": "photoshop"
}

def get_all_installed_apps() -> List[Dict[str, str]]:
    """Query and cache all installed Windows 11 StartApps."""
    global _installed_apps_cache, _last_cache_time
    now = time.time()
    if _installed_apps_cache and (now - _last_cache_time) < 600:
        return _installed_apps_cache

    try:
        cmd = ["powershell.exe", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        if res.returncode == 0 and res.stdout.strip():
            raw = json.loads(res.stdout.strip())
            if isinstance(raw, list):
                _installed_apps_cache = [{"name": a.get("Name", ""), "appid": a.get("AppID", "")} for a in raw if a.get("Name") and a.get("AppID")]
            elif isinstance(raw, dict):
                _installed_apps_cache = [{"name": raw.get("Name", ""), "appid": raw.get("AppID", "")}]
            _last_cache_time = now
    except Exception:
        pass

    return _installed_apps_cache

class PCControlService:
    @staticmethod
    def get_system_status() -> Dict[str, Any]:
        """Collect current Windows system metrics (CPU, RAM, Disk, Battery, GPU)."""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("C:\\")
        
        battery = None
        try:
            b = psutil.sensors_battery()
            if b:
                battery = {
                    "percent": b.percent,
                    "power_plugged": b.power_plugged,
                    "secs_left": b.secsleft
                }
        except Exception:
            pass

        # GPU metrics using nvidia-smi if available
        gpu_info = None
        try:
            cmd = ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 4:
                    gpu_info = {
                        "model": parts[0],
                        "total_vram_mb": int(parts[1]),
                        "used_vram_mb": int(parts[2]),
                        "free_vram_mb": int(parts[3]),
                        "temperature_c": int(parts[4]) if len(parts) > 4 else None
                    }
        except Exception:
            pass

        return {
            "platform": "Windows 11",
            "cpu_percent": cpu_percent,
            "ram_total_gb": round(ram.total / (1024**3), 2),
            "ram_used_gb": round(ram.used / (1024**3), 2),
            "ram_percent": ram.percent,
            "disk_free_gb": round(disk.free / (1024**3), 2),
            "disk_percent": disk.percent,
            "battery": battery,
            "gpu": gpu_info
        }

    @staticmethod
    def open_app(app_name: str) -> Dict[str, Any]:
        """
        Full access PC application launcher for Windows 11:
        1. Checks well-known protocols/binaries (WhatsApp, Spotify, VS Code, Chrome, etc.)
        2. Dynamically scans installed Windows StartApps (UWP & Win32)
        3. Attempts direct Windows shell execution
        """
        clean_name = app_name.strip().lower()
        clean_name = re.sub(r"^(?:the\s+)?app\s+", "", clean_name)
        clean_name = re.sub(r"\s+app$", "", clean_name).strip()

        # Step 1: Check known launchers & protocols
        if clean_name in KNOWN_APP_LAUNCHERS:
            target = KNOWN_APP_LAUNCHERS[clean_name]
            try:
                if target.endswith(":"):
                    subprocess.Popen(f"cmd.exe /c start {target}", shell=True)
                else:
                    subprocess.Popen(f"cmd.exe /c start \"\" {target}", shell=True)
                
                log_action("open_app", clean_name, "success", {"target": target})
                return {
                    "success": True,
                    "message": f"Successfully launched {app_name.title()} on your Windows 11 PC.",
                    "app": clean_name
                }
            except Exception as ex:
                pass

        # Step 2: Search installed Windows StartApps dynamically
        installed = get_all_installed_apps()
        matched_app = None
        
        # Priority A: Exact match
        for a in installed:
            if a["name"].lower() == clean_name:
                matched_app = a
                break
                
        # Priority B: Substring / Word match
        if not matched_app:
            for a in installed:
                if clean_name in a["name"].lower() or a["name"].lower().startswith(clean_name):
                    matched_app = a
                    break

        if matched_app:
            appid = matched_app["appid"]
            app_title = matched_app["name"]
            try:
                # Launch via shell:AppsFolder
                subprocess.Popen(f'cmd.exe /c start "" "shell:AppsFolder\\{appid}"', shell=True)
                log_action("open_app", clean_name, "success", {"appid": appid, "title": app_title})
                return {
                    "success": True,
                    "message": f"Successfully launched {app_title} on your Windows 11 PC.",
                    "app": app_title
                }
            except Exception as e:
                pass

        # Step 3: Generic shell launch fallback
        try:
            subprocess.Popen(f"cmd.exe /c start \"\" \"{clean_name}\"", shell=True)
            log_action("open_app", clean_name, "success", {"fallback": clean_name})
            return {
                "success": True,
                "message": f"Sent launch command for '{app_name.title()}' to Windows 11.",
                "app": clean_name
            }
        except Exception as e:
            log_action("open_app", clean_name, "error", {"error": str(e)})
            return {
                "success": False,
                "message": f"Could not launch application '{app_name}': {str(e)}"
            }

    @staticmethod
    def open_website(url: str) -> Dict[str, Any]:
        """Open a website in the default browser."""
        target = url.strip()
        if not target.startswith("http://") and not target.startswith("https://"):
            target = "https://" + target

        try:
            parsed = urlparse(target)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]

            webbrowser.open(target)
            log_action("open_website", target, "success", {"domain": domain})
            return {
                "success": True,
                "message": f"Opened {domain} in your default browser.",
                "url": target
            }
        except Exception as e:
            return {"success": False, "message": f"Failed to open website: {str(e)}"}

    @staticmethod
    def create_pending_confirmation(action_type: str, description: str, payload: Dict[str, Any]) -> str:
        """Create a safety confirmation ticket for sensitive operations."""
        conf_id = str(uuid.uuid4())[:8]
        get_sync_db().pending_confirmations.insert_one({
            "id": conf_id,
            "action_type": action_type,
            "description": description,
            "payload": payload,
            "status": "pending",
        })
        return conf_id

    @staticmethod
    def resolve_confirmation(conf_id: str, approved: bool) -> Dict[str, Any]:
        """User explicitly approves or rejects a pending sensitive operation."""
        db = get_sync_db()
        row = db.pending_confirmations.find_one({"id": conf_id, "status": "pending"})
        if not row:
            return {"success": False, "message": "Confirmation request not found or already processed."}

        action_type = row["action_type"]
        payload = row["payload"]
        new_status = "approved" if approved else "rejected"
        db.pending_confirmations.update_one({"id": conf_id}, {"$set": {"status": new_status}})

        if approved:
            if action_type == "open_website":
                webbrowser.open(payload["url"])
                return {"success": True, "message": f"Approved and opened {payload['url']}."}
            elif action_type == "delete_file":
                return {"success": True, "message": f"Approved deletion of {payload['path']}."}
        
        return {"success": True, "message": f"Action {conf_id} was successfully {new_status}."}

pc_control_service = PCControlService()
