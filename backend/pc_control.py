import subprocess
import webbrowser
import psutil
import uuid
import json
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse
from backend.config import settings
from backend.database import log_action
from backend.mongodb import get_sync_db

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
        """Launch an approved application from the allowlist."""
        normalized = app_name.strip().lower()
        if normalized not in settings.APPROVED_APPS:
            log_action("open_app", app_name, "rejected", {"reason": "Not in approved apps allowlist"})
            return {
                "success": False,
                "message": f"Application '{app_name}' is not in the approved applications list.",
                "allowed_apps": list(settings.APPROVED_APPS.keys())
            }

        executable = settings.APPROVED_APPS[normalized]
        try:
            if normalized in ("vscode", "code"):
                subprocess.Popen("cmd.exe /c start \"\" code", shell=True)
            elif normalized in ("calc", "calculator"):
                subprocess.Popen("cmd.exe /c start \"\" calc.exe", shell=True)
            elif normalized == "notepad":
                subprocess.Popen("cmd.exe /c start \"\" notepad.exe", shell=True)
            elif normalized in ("explorer", "file explorer"):
                subprocess.Popen("cmd.exe /c start \"\" explorer.exe", shell=True)
            elif normalized == "paint":
                subprocess.Popen("cmd.exe /c start \"\" mspaint.exe", shell=True)
            elif executable == "start":
                subprocess.Popen("cmd.exe /c start", shell=True)
            else:
                subprocess.Popen(f"cmd.exe /c start \"\" {executable}", shell=True)

            log_action("open_app", normalized, "success", {"executable": executable})
            return {
                "success": True,
                "message": f"Successfully launched {app_name.capitalize()} on your PC.",
                "app": normalized
            }
        except Exception as e:
            log_action("open_app", normalized, "error", {"error": str(e)})
            return {
                "success": False,
                "message": f"Could not launch {app_name}: {str(e)}"
            }

    @staticmethod
    def open_website(url: str) -> Dict[str, Any]:
        """Open an approved website in default browser."""
        target = url.strip()
        if not target.startswith("http://") and not target.startswith("https://"):
            target = "https://" + target

        try:
            parsed = urlparse(target)
            domain = parsed.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]

            # Check if domain matches or belongs to approved list
            approved = any(domain == app or domain.endswith("." + app) for app in settings.APPROVED_WEBSITES)
            if not approved:
                # Require confirmation for unlisted website
                conf_id = PCControlService.create_pending_confirmation(
                    action_type="open_website",
                    description=f"Open unlisted website: {target}",
                    payload={"url": target}
                )
                return {
                    "success": False,
                    "needs_confirmation": True,
                    "confirmation_id": conf_id,
                    "message": f"Website '{domain}' is not in the default allowlist. Jenni AI needs your confirmation to open it."
                }

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
                # Simulated safe delete execution
                return {"success": True, "message": f"Approved deletion of {payload['path']}."}
        
        return {"success": True, "message": f"Action {conf_id} was successfully {new_status}."}

pc_control_service = PCControlService()
