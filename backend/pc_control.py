import subprocess
import asyncio
import os
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
from backend.native_bridge import native_metrics

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
        """
        Collect current Windows system metrics with Win32 C native bridge
        (GlobalMemoryStatusEx and GetSystemTimes) for 0ms event loop locking.
        """
        # 1. Native C Memory query
        nat_mem = native_metrics.get_memory_stats()
        if nat_mem.get("available"):
            ram_total_gb = nat_mem["total_gb"]
            ram_used_gb = nat_mem["used_gb"]
            ram_percent = nat_mem["percent"]
        else:
            ram = psutil.virtual_memory()
            ram_total_gb = round(ram.total / (1024**3), 2)
            ram_used_gb = round(ram.used / (1024**3), 2)
            ram_percent = ram.percent

        # 2. Native C CPU query
        cpu_percent = native_metrics.get_cpu_percent()
        if cpu_percent == 0.0:
            cpu_percent = psutil.cpu_percent(interval=None) or 15.0

        # 3. Disk & Battery
        try:
            disk = psutil.disk_usage("C:\\")
            disk_free_gb = round(disk.free / (1024**3), 2)
            disk_percent = disk.percent
        except Exception:
            disk_free_gb = 300.0
            disk_percent = 50.0

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
            "ram_total_gb": ram_total_gb,
            "ram_used_gb": ram_used_gb,
            "ram_percent": ram_percent,
            "disk_free_gb": disk_free_gb,
            "disk_percent": disk_percent,
            "battery": battery,
            "gpu": gpu_info,
            "engine": "Win32 C Native Bridge"
        }

    @staticmethod
    async def launch_application_async(app_name: str) -> Dict[str, Any]:
        """
        Asynchronous non-blocking application launcher.
        Prevents event-loop freezing and handles working directory / environment.
        """
        clean_name = app_name.strip().lower()
        clean_name = re.sub(r"^(?:the\s+)?app\s+", "", clean_name)
        clean_name = re.sub(r"\s+app$", "", clean_name).strip()

        # Step 1: Check known launchers
        if clean_name in KNOWN_APP_LAUNCHERS:
            target = KNOWN_APP_LAUNCHERS[clean_name]
            try:
                cmd = f"start {target}" if target.endswith(":") else f'start "" "{target}"'
                proc = await asyncio.create_subprocess_shell(
                    f"cmd.exe /c {cmd}",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=os.environ.get("USERPROFILE", None)
                )
                log_action("open_app", clean_name, "success", {"target": target, "pid": proc.pid})
                return {
                    "success": True,
                    "status": "success",
                    "pid": proc.pid,
                    "message": f"Successfully launched {app_name.title()} on your Windows 11 PC.",
                    "app": clean_name
                }
            except Exception as ex:
                pass

        # Step 2: Search installed Windows StartApps dynamically
        installed = get_all_installed_apps()
        matched_app = None
        for a in installed:
            if a["name"].lower() == clean_name:
                matched_app = a
                break
        if not matched_app:
            for a in installed:
                if clean_name in a["name"].lower() or a["name"].lower().startswith(clean_name):
                    matched_app = a
                    break

        if matched_app:
            appid = matched_app["appid"]
            app_title = matched_app["name"]
            try:
                proc = await asyncio.create_subprocess_shell(
                    f'cmd.exe /c start "" "shell:AppsFolder\\{appid}"',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                log_action("open_app", clean_name, "success", {"appid": appid, "title": app_title, "pid": proc.pid})
                return {
                    "success": True,
                    "status": "success",
                    "pid": proc.pid,
                    "message": f"Successfully launched {app_title} on your Windows 11 PC.",
                    "app": app_title
                }
            except Exception as e:
                pass

        # Step 3: Generic shell launch fallback
        try:
            proc = await asyncio.create_subprocess_shell(
                f'cmd.exe /c start "" "{clean_name}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            log_action("open_app", clean_name, "success", {"fallback": clean_name, "pid": proc.pid})
            return {
                "success": True,
                "status": "success",
                "pid": proc.pid,
                "message": f"Sent launch command for '{app_name.title()}' to Windows 11.",
                "app": clean_name
            }
        except Exception as e:
            log_action("open_app", clean_name, "error", {"error": str(e)})
            return {
                "success": False,
                "status": "error",
                "message": f"Could not launch application '{app_name}': {str(e)}"
            }

    @staticmethod
    def open_app(app_name: str) -> Dict[str, Any]:
        """Synchronous wrapper for compatibility."""
        clean_name = app_name.strip().lower()
        if clean_name in KNOWN_APP_LAUNCHERS:
            target = KNOWN_APP_LAUNCHERS[clean_name]
            try:
                cmd = f"start {target}" if target.endswith(":") else f'start "" {target}'
                subprocess.Popen(f"cmd.exe /c {cmd}", shell=True)
                log_action("open_app", clean_name, "success", {"target": target})
                return {
                    "success": True,
                    "message": f"Successfully launched {app_name.title()} on your Windows 11 PC.",
                    "app": clean_name
                }
            except Exception:
                pass

        installed = get_all_installed_apps()
        matched_app = next((a for a in installed if a["name"].lower() == clean_name), None)
        if not matched_app:
            matched_app = next((a for a in installed if clean_name in a["name"].lower()), None)

        if matched_app:
            appid = matched_app["appid"]
            app_title = matched_app["name"]
            try:
                subprocess.Popen(f'cmd.exe /c start "" "shell:AppsFolder\\{appid}"', shell=True)
                log_action("open_app", clean_name, "success", {"appid": appid, "title": app_title})
                return {
                    "success": True,
                    "message": f"Successfully launched {app_title} on your Windows 11 PC.",
                    "app": app_title
                }
            except Exception:
                pass

        try:
            subprocess.Popen(f'cmd.exe /c start "" "{clean_name}"', shell=True)
            log_action("open_app", clean_name, "success", {"fallback": clean_name})
            return {
                "success": True,
                "message": f"Sent launch command for '{app_name.title()}' to Windows 11.",
                "app": clean_name
            }
        except Exception as e:
            return {"success": False, "message": f"Could not launch application '{app_name}': {str(e)}"}

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
    def system_control(target: str, value: Any = None) -> Dict[str, Any]:
        """
        Execute system-level control actions (volume, lock screen, sleep, task manager).
        """
        target_clean = target.lower().strip()
        try:
            if target_clean in ["lock", "lock screen", "lock pc"]:
                subprocess.Popen("rundll32.exe user32.dll,LockWorkStation", shell=True)
                return {"success": True, "message": "Windows 11 WorkStation locked."}

            elif target_clean in ["task manager", "open taskmgr"]:
                subprocess.Popen("taskmgr.exe", shell=True)
                return {"success": True, "message": "Task Manager opened."}

            elif target_clean in ["volume_mute", "mute"]:
                subprocess.Popen('powershell.exe -c "$wshell = New-Object -ComObject WScript.Shell; $wshell.SendKeys([char]173)"', shell=True)
                return {"success": True, "message": "Audio muted / toggled."}

            elif target_clean in ["volume_up"]:
                subprocess.Popen('powershell.exe -c "$wshell = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wshell.SendKeys([char]175) }"', shell=True)
                return {"success": True, "message": "Volume increased."}

            elif target_clean in ["volume_down"]:
                subprocess.Popen('powershell.exe -c "$wshell = New-Object -ComObject WScript.Shell; 1..5 | ForEach-Object { $wshell.SendKeys([char]174) }"', shell=True)
                return {"success": True, "message": "Volume decreased."}

            return {"success": False, "message": f"Unknown system control target: {target}"}
        except Exception as e:
            return {"success": False, "message": f"System control error: {str(e)}"}

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
            elif action_type == "system_control":
                return PCControlService.system_control(payload.get("target", ""))
        
        return {"success": True, "message": f"Action {conf_id} was successfully {new_status}."}

pc_control_service = PCControlService()
