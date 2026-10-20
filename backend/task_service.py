import asyncio
import uuid
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from backend.pc_control import pc_control_service
from backend.memory_service import memory_service
from backend.database import get_connection, log_action

# Active running task controls
_RUNNING_TASKS: Dict[str, Dict[str, Any]] = {}

PREDEFINED_WORKFLOWS = [
    {
        "id": "wf_dev_setup",
        "title": "Developer Workspace Launch",
        "description": "Prepares your coding workspace: checks resources, launches VS Code, and opens GitHub.",
        "steps": [
            {"id": 1, "name": "Check Hardware Health", "action": "check_status"},
            {"id": 2, "name": "Launch VS Code", "action": "open_app", "target": "vscode"},
            {"id": 3, "name": "Open GitHub", "action": "open_website", "target": "github.com"}
        ]
    },
    {
        "id": "wf_daily_briefing",
        "title": "Jenni AI Daily Briefing",
        "description": "Summarizes system health, active user preferences, and prepares Jenni AI.",
        "steps": [
            {"id": 1, "name": "Query System Metrics", "action": "check_status"},
            {"id": 2, "name": "Review Personal Preferences", "action": "review_memories"},
            {"id": 3, "name": "Jenni AI Greeting Voice Check", "action": "greeting_check"}
        ]
    },
    {
        "id": "wf_deep_health_check",
        "title": "Comprehensive PC & GPU Diagnostics",
        "description": "Runs complete diagnostics on CPU, RAM, Disk and NVIDIA RTX 3050 VRAM.",
        "steps": [
            {"id": 1, "name": "CPU & Memory Utilization", "action": "check_status"},
            {"id": 2, "name": "Storage Space Inspection", "action": "check_disk"},
            {"id": 3, "name": "GPU VRAM & Temperature", "action": "check_gpu"}
        ]
    }
]

class TaskService:
    @staticmethod
    def list_workflows() -> List[Dict[str, Any]]:
        """Return available workflow templates."""
        return PREDEFINED_WORKFLOWS

    @staticmethod
    def get_task_history(limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieve recent task execution logs."""
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            tasks = []
            for r in rows:
                t = dict(r)
                t["steps"] = json.loads(t["steps"]) if t["steps"] else []
                tasks.append(t)
            return tasks

    @staticmethod
    async def run_workflow(workflow_id: str) -> Dict[str, Any]:
        """Start execution of a multi-step workflow asynchronously."""
        wf = next((w for w in PREDEFINED_WORKFLOWS if w["id"] == workflow_id), None)
        if not wf:
            return {"success": False, "message": f"Workflow {workflow_id} not found."}

        task_id = str(uuid.uuid4())[:8]
        steps = [dict(s, status="pending", result=None) for s in wf["steps"]]

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO tasks (id, title, description, steps, current_step, status) VALUES (?, ?, ?, ?, 0, 'running')",
                (task_id, wf["title"], wf["description"], json.dumps(steps))
            )
            conn.commit()

        _RUNNING_TASKS[task_id] = {
            "cancelled": False,
            "status": "running"
        }

        # Run workflow in background task
        asyncio.create_task(TaskService._execute_task_steps(task_id, steps))

        return {
            "success": True,
            "task_id": task_id,
            "title": wf["title"],
            "status": "running",
            "message": f"Started workflow: {wf['title']}"
        }

    @staticmethod
    async def _execute_task_steps(task_id: str, steps: List[Dict[str, Any]]):
        try:
            for idx, step in enumerate(steps):
                # Check if task was cancelled by user
                if task_id in _RUNNING_TASKS and _RUNNING_TASKS[task_id].get("cancelled"):
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                        conn.commit()
                    log_action("task_cancelled", task_id, "cancelled")
                    return

                # Mark step as running
                step["status"] = "running"
                TaskService._update_task_record(task_id, steps, idx, "running")

                # Simulate small step delay for realistic progression
                await asyncio.sleep(0.8)

                # Execute action
                act = step.get("action")
                target = step.get("target")

                result_text = "Completed"
                if act == "open_app":
                    res = pc_control_service.open_app(target)
                    result_text = res.get("message", "App launched")
                elif act == "open_website":
                    res = pc_control_service.open_website(target)
                    result_text = res.get("message", "Website opened")
                elif act == "check_status":
                    stats = pc_control_service.get_system_status()
                    result_text = f"CPU: {stats['cpu_percent']}%, RAM: {stats['ram_percent']}%"
                elif act == "check_disk":
                    stats = pc_control_service.get_system_status()
                    result_text = f"C: Free {stats['disk_free_gb']} GB ({100 - stats['disk_percent']}% free)"
                elif act == "check_gpu":
                    stats = pc_control_service.get_system_status()
                    gpu = stats.get("gpu")
                    result_text = f"{gpu['model'] if gpu else 'Integrated'} - {gpu['free_vram_mb'] if gpu else 0} MB Free"
                elif act == "review_memories":
                    memories = memory_service.list_memories()
                    result_text = f"{len(memories)} user preferences currently active"
                elif act == "greeting_check":
                    result_text = "Jenni AI online and awaiting voice commands"

                step["status"] = "completed"
                step["result"] = result_text
                TaskService._update_task_record(task_id, steps, idx + 1, "running" if idx + 1 < len(steps) else "completed")

            # Finalize task
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                conn.commit()
            log_action("task_completed", task_id, "success")

        except Exception as e:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET status = 'failed', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                conn.commit()
            log_action("task_failed", task_id, "error", {"error": str(e)})

    @staticmethod
    def _update_task_record(task_id: str, steps: List[Dict[str, Any]], current_step: int, status: str):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET steps = ?, current_step = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(steps), current_step, status, task_id)
            )
            conn.commit()

    @staticmethod
    def cancel_task(task_id: str) -> Dict[str, Any]:
        """Stop and cancel a running task workflow."""
        if task_id in _RUNNING_TASKS:
            _RUNNING_TASKS[task_id]["cancelled"] = True
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE tasks SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?", (task_id,))
                conn.commit()
            return {"success": True, "message": f"Task {task_id} has been cancelled."}

        return {"success": False, "message": f"Task {task_id} is not currently running."}

task_service = TaskService()
