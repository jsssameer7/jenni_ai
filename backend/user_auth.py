"""
MongoDB-backed user authentication for Jenni AI.
Handles registration, login, session tokens, and password hashing.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

from bson import ObjectId

from backend.config import settings
from backend.mongodb import get_sync_db


# ── Helpers ─────────────────────────────────────────────────────────────────

def _db():
    return get_sync_db()


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}:{settings.SECRET_KEY}".encode()).hexdigest()


def _now() -> datetime:
    return datetime.utcnow()


# ── Init ─────────────────────────────────────────────────────────────────────

def init_users_table():
    """
    Seed a default admin user if the users collection is empty.
    Indexes are created by mongodb.init_mongo() → _create_indexes().
    """
    _seed_default_user()


def _seed_default_user():
    db = _db()
    if db.users.count_documents({}) == 0:
        salt = secrets.token_hex(16)
        pw_hash = _hash_password("jenni123", salt)
        db.users.insert_one(
            {
                "username": "admin",
                "display_name": "Sameer",
                "password_hash": pw_hash,
                "salt": salt,
                "role": "admin",
                "created_at": _now(),
                "last_login": None,
            }
        )
        print("[Jenni Auth] Default user created: username=admin  password=jenni123")


# ── Registration ──────────────────────────────────────────────────────────────

def create_user(
    username: str, display_name: str, password: str, role: str = "user"
) -> Dict[str, Any]:
    """Register a new user. Raises ValueError if username is already taken."""
    db = _db()
    if db.users.find_one({"username": {"$regex": f"^{re.escape(username.strip())}$", "$options": "i"}}):
        raise ValueError(f"Username '{username}' is already taken.")

    salt = secrets.token_hex(16)
    pw_hash = _hash_password(password, salt)
    result = db.users.insert_one(
        {
            "username": username.strip(),
            "display_name": display_name.strip(),
            "password_hash": pw_hash,
            "salt": salt,
            "role": role,
            "created_at": _now(),
            "last_login": None,
        }
    )
    return {
        "id": str(result.inserted_id),
        "username": username.strip(),
        "display_name": display_name.strip(),
        "role": role,
    }


# ── Login ─────────────────────────────────────────────────────────────────────

def login_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify credentials and return session token dict, or None if invalid."""
    import re as _re
    db = _db()
    user = db.users.find_one(
        {"username": {"$regex": f"^{_re.escape(username.strip())}$", "$options": "i"}}
    )
    if not user:
        return None

    expected = _hash_password(password, user["salt"])
    if not hmac.compare_digest(expected, user["password_hash"]):
        return None

    # Create session (30 days)
    token = secrets.token_urlsafe(48)
    expires_at = _now() + timedelta(days=30)

    db.user_sessions.insert_one(
        {
            "user_id": user["_id"],
            "token": token,
            "created_at": _now(),
            "expires_at": expires_at,
        }
    )
    db.users.update_one({"_id": user["_id"]}, {"$set": {"last_login": _now()}})

    return {
        "token": token,
        "user": {
            "id": str(user["_id"]),
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
        "expires_at": expires_at.isoformat(),
    }


# ── Session verify ────────────────────────────────────────────────────────────

def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """Return user info for a valid, non-expired token, else None."""
    db = _db()
    session = db.user_sessions.find_one({"token": token})
    if not session:
        return None

    # Check expiry (MongoDB TTL index will clean up, but double-check)
    if _now() > session["expires_at"]:
        return None

    user = db.users.find_one({"_id": session["user_id"]})
    if not user:
        return None

    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


# ── Logout ────────────────────────────────────────────────────────────────────

def logout_user(token: str) -> bool:
    result = _db().user_sessions.delete_one({"token": token})
    return result.deleted_count > 0


# ── Admin helpers ─────────────────────────────────────────────────────────────

def list_users() -> List[Dict[str, Any]]:
    cursor = _db().users.find().sort("created_at", 1)
    out = []
    for u in cursor:
        out.append(
            {
                "id": str(u["_id"]),
                "username": u["username"],
                "display_name": u["display_name"],
                "role": u["role"],
                "created_at": u.get("created_at", "").isoformat() if isinstance(u.get("created_at"), datetime) else str(u.get("created_at", "")),
                "last_login": u.get("last_login", "").isoformat() if isinstance(u.get("last_login"), datetime) else str(u.get("last_login", "")),
            }
        )
    return out


# re imported at module level for create_user
import re
