import sqlite3
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from backend.config import settings

# Sensitive keyword patterns that must NEVER be saved into memory
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
    r"\bpin\b"
]

def get_connection() -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode enabled."""
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def init_db():
    """Initialize all required tables for Jenni AI."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Chat conversations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL DEFAULT 'default',
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                model TEXT NOT NULL DEFAULT 'qwen2.5:3b',
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id, created_at);")

        # 2. Personal memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL DEFAULT 'preference',
                key TEXT NOT NULL UNIQUE,
                value TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_memories_key ON memories(key);")

        # 3. Safe PC action audit logs
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS action_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                details TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 4. Multi-step tasks
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                steps TEXT NOT NULL,
                current_step INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # 5. Pending safety confirmations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                description TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        conn.commit()

# --- Conversation Methods ---

def add_message(role: str, content: str, session_id: str = "default", model: str = "qwen2.5:3b", metadata: Optional[Dict] = None) -> int:
    meta_str = json.dumps(metadata) if metadata else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO conversations (session_id, role, content, model, metadata) VALUES (?, ?, ?, ?, ?)",
            (session_id, role, content, model, meta_str)
        )
        conn.commit()
        return cursor.lastrowid

def get_recent_messages(session_id: str = "default", limit: int = 20) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, session_id, role, content, model, metadata, created_at 
            FROM conversations 
            WHERE session_id = ? 
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (session_id, limit)
        )
        rows = cursor.fetchall()
        result = []
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            result.append({
                "id": r["id"],
                "session_id": r["session_id"],
                "role": r["role"],
                "content": r["content"],
                "model": r["model"],
                "metadata": meta,
                "created_at": r["created_at"]
            })
        return result

def clear_conversation_history(session_id: str = "default") -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM conversations WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount

# --- Memory Methods ---

def is_sensitive_content(text: str) -> bool:
    """Check if the text contains sensitive credentials like passwords, tokens or API keys."""
    text_lower = text.lower()
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def save_memory(key: str, value: str, category: str = "preference") -> Dict[str, Any]:
    """Store or update a memory preference with security sanitization."""
    cleaned_key = key.strip().lower()
    cleaned_val = value.strip()

    if is_sensitive_content(cleaned_key) or is_sensitive_content(cleaned_val):
        raise ValueError("Security violation: Jenni AI is configured never to store passwords, tokens, or secret keys.")

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO memories (category, key, value, updated_at) 
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET 
                value = excluded.value,
                category = excluded.category,
                updated_at = CURRENT_TIMESTAMP
        """, (category, cleaned_key, cleaned_val))
        conn.commit()
        return {"key": cleaned_key, "value": cleaned_val, "category": category, "status": "saved"}

def get_all_memories() -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, category, key, value, created_at, updated_at FROM memories ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

def delete_memory(memory_id: int) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        conn.commit()
        return cursor.rowcount > 0

def delete_memory_by_key(key: str) -> bool:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM memories WHERE key = ?", (key.strip().lower(),))
        conn.commit()
        return cursor.rowcount > 0

# --- Audit Logs ---

def log_action(action_type: str, command: str, status: str, details: Optional[Dict] = None):
    details_str = json.dumps(details) if details else None
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO action_logs (action_type, command, status, details) VALUES (?, ?, ?, ?)",
            (action_type, command, status, details_str)
        )
        conn.commit()

def get_recent_action_logs(limit: int = 50) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM action_logs ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        logs = []
        for r in rows:
            d = dict(r)
            d["details"] = json.loads(d["details"]) if d["details"] else {}
            logs.append(d)
        return logs
