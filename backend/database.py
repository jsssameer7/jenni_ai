"""
MongoDB-backed database layer for Jenni AI.
Replaces the original SQLite implementation while keeping the same
public function signatures so existing callers are not broken.
"""
import re
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

from backend.mongodb import get_sync_db

# Sensitive keyword patterns — never save into memory
SENSITIVE_PATTERNS = [
    r"password",
    r"api[_-]?key",
    r"secret[_-]?key",
    r"bearer\s+[a-zA-Z0-9_\-\.]+",
    r"token",
    r"private[_-]?key",
    r"credentials?",
    r"credit[_-]?card",
    r"cvv",
    r"\bpin\b",
]


def init_db():
    """No-op — indexes are created by mongodb.init_mongo(). Kept for compatibility."""
    pass


# ── Helpers ────────────────────────────────────────────────────────────────

def _db():
    return get_sync_db()


def _now() -> str:
    return datetime.utcnow().isoformat()


# ── Conversation / Chat ────────────────────────────────────────────────────

def add_message(
    role: str,
    content: str,
    session_id: str = "default",
    model: str = "qwen2.5:3b",
    metadata: Optional[Dict] = None,
) -> str:
    doc = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "model": model,
        "metadata": metadata or {},
        "created_at": _now(),
    }
    result = _db().conversations.insert_one(doc)
    return str(result.inserted_id)


def get_recent_messages(session_id: str = "default", limit: int = 20) -> List[Dict[str, Any]]:
    cursor = (
        _db()
        .conversations.find({"session_id": session_id})
        .sort("created_at", 1)
        .limit(limit)
    )
    out = []
    for r in cursor:
        out.append(
            {
                "id": str(r["_id"]),
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "model": r.get("model", ""),
                "metadata": r.get("metadata", {}),
                "created_at": r.get("created_at", ""),
            }
        )
    return out


def clear_conversation_history(session_id: str = "default") -> int:
    result = _db().conversations.delete_many({"session_id": session_id})
    return result.deleted_count


# ── Personal Memory ────────────────────────────────────────────────────────

def is_sensitive_content(text: str) -> bool:
    text_lower = text.lower()
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False


def save_memory(key: str, value: str, category: str = "preference") -> Dict[str, Any]:
    cleaned_key = key.strip().lower()
    cleaned_val = value.strip()

    if is_sensitive_content(cleaned_key) or is_sensitive_content(cleaned_val):
        raise ValueError(
            "Security violation: Jenni AI is configured never to store passwords, tokens, or secret keys."
        )

    now = _now()
    _db().memories.update_one(
        {"key": cleaned_key},
        {
            "$set": {
                "key": cleaned_key,
                "value": cleaned_val,
                "category": category,
                "updated_at": now,
            },
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {"key": cleaned_key, "value": cleaned_val, "category": category, "status": "saved"}


def get_all_memories() -> List[Dict[str, Any]]:
    cursor = _db().memories.find().sort("updated_at", -1)
    out = []
    for r in cursor:
        out.append(
            {
                "id": str(r["_id"]),
                "category": r.get("category", "preference"),
                "key": r["key"],
                "value": r["value"],
                "created_at": r.get("created_at", ""),
                "updated_at": r.get("updated_at", ""),
            }
        )
    return out


def delete_memory(memory_id: str) -> bool:
    from bson import ObjectId
    try:
        result = _db().memories.delete_one({"_id": ObjectId(memory_id)})
        return result.deleted_count > 0
    except Exception:
        return False


def delete_memory_by_key(key: str) -> bool:
    result = _db().memories.delete_one({"key": key.strip().lower()})
    return result.deleted_count > 0


# ── Audit Logs ─────────────────────────────────────────────────────────────

def log_action(action_type: str, command: str, status: str, details: Optional[Dict] = None):
    try:
        _db().action_logs.insert_one(
            {
                "action_type": action_type,
                "command": command,
                "status": status,
                "details": details or {},
                "created_at": _now(),
            }
        )
    except Exception:
        pass


def get_recent_action_logs(limit: int = 50) -> List[Dict[str, Any]]:
    cursor = _db().action_logs.find().sort("created_at", -1).limit(limit)
    out = []
    for r in cursor:
        out.append(
            {
                "id": str(r["_id"]),
                "action_type": r["action_type"],
                "command": r["command"],
                "status": r["status"],
                "details": r.get("details", {}),
                "created_at": r.get("created_at", ""),
            }
        )
    return out
