import os
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.config import settings
from backend.database import log_action

class FileService:
    @staticmethod
    def get_allowed_roots() -> List[Path]:
        return settings.approved_directories

    @staticmethod
    def is_safe_path(target_path: Path) -> bool:
        """Verify that target_path is within one of the approved root directories."""
        try:
            resolved = target_path.resolve()
            for root in settings.approved_directories:
                resolved_root = root.resolve()
                if resolved == resolved_root or resolved_root in resolved.parents:
                    return True
            return False
        except Exception:
            return False

    @staticmethod
    def search_files(
        query: str,
        folder: Optional[str] = None,
        extension: Optional[str] = None,
        max_results: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search approved folders for files matching query and/or extension.
        """
        results = []
        search_roots = []

        if folder:
            candidate = Path(folder).resolve()
            if FileService.is_safe_path(candidate) and candidate.is_dir():
                search_roots = [candidate]
            else:
                return []
        else:
            search_roots = settings.approved_directories

        clean_query = query.strip().lower()
        clean_ext = extension.strip().lower() if extension else None
        if clean_ext and not clean_ext.startswith("."):
            clean_ext = "." + clean_ext

        for root in search_roots:
            if not root.exists():
                continue
            try:
                for entry in root.rglob("*"):
                    # Avoid traversing deeply into hidden or massive directories like venv, node_modules, .git
                    parts = entry.parts
                    if any(ignored in parts for ignored in ["venv", "node_modules", ".git", ".ollama", "__pycache__", "AppData"]):
                        continue

                    name_lower = entry.name.lower()

                    # Match query
                    if clean_query and clean_query not in name_lower:
                        continue

                    # Match extension
                    if clean_ext and entry.suffix.lower() != clean_ext:
                        continue

                    try:
                        stat = entry.stat()
                        results.append({
                            "name": entry.name,
                            "path": str(entry.resolve()),
                            "is_dir": entry.is_dir(),
                            "size_bytes": stat.st_size if not entry.is_dir() else 0,
                            "size_kb": round(stat.st_size / 1024, 1) if not entry.is_dir() else 0,
                            "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                        })
                    except (PermissionError, FileNotFoundError):
                        continue

                    if len(results) >= max_results:
                        break
            except (PermissionError, OSError):
                continue

            if len(results) >= max_results:
                break

        return results

    @staticmethod
    def open_or_reveal_file(file_path: str, reveal: bool = False) -> Dict[str, Any]:
        """Safely open the file or show it selected in Windows Explorer."""
        p = Path(file_path)
        if not FileService.is_safe_path(p):
            log_action("open_file", file_path, "rejected", {"reason": "Path traversal or outside approved folders"})
            return {"success": False, "message": "Access denied: File is outside approved directories."}

        if not p.exists():
            return {"success": False, "message": "File does not exist."}

        try:
            if reveal:
                # Open Explorer with file highlighted
                subprocess.Popen(["explorer.exe", f"/select,{str(p.resolve())}"])
                return {"success": True, "message": f"Revealed {p.name} in Windows Explorer."}
            else:
                # Open with Windows default application
                os.startfile(str(p.resolve()))
                return {"success": True, "message": f"Opened {p.name}."}
        except Exception as e:
            return {"success": False, "message": f"Could not open file: {str(e)}"}

file_service = FileService()
