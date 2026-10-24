"""
MongoDB connection and collection helpers for Jenni AI.
Uses Motor (async) for FastAPI endpoints and PyMongo (sync) for startup/auth.
URI and DB name are read from .env / config.
"""
from __future__ import annotations

import logging
from typing import Optional

import pymongo
from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from backend.config import settings

logger = logging.getLogger("jenni.mongodb")

# ── Sync client (used during startup / user_auth) ──────────────────────────
_sync_client: Optional[MongoClient] = None
_sync_db = None

# ── Async client (used in FastAPI route handlers) ──────────────────────────
_async_client: Optional[AsyncIOMotorClient] = None
_async_db: Optional[AsyncIOMotorDatabase] = None


# ── Initialise both clients ─────────────────────────────────────────────────
def init_mongo():
    """Connect to MongoDB and create indexes. Call once at app startup."""
    global _sync_client, _sync_db, _async_client, _async_db

    uri = settings.MONGODB_URI
    db_name = settings.MONGODB_DB

    # Sync client
    _sync_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    _sync_db = _sync_client[db_name]

    # Async client
    _async_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    _async_db = _async_client[db_name]

    # Verify connection
    try:
        _sync_client.admin.command("ping")
        logger.info(f"[MongoDB] Connected → {uri} / db={db_name}")
        print(f"  [MongoDB] ✓ Connected → {uri}  db={db_name}")
    except Exception as e:
        logger.error(f"[MongoDB] Connection failed: {e}")
        print(f"  [MongoDB] ✗ Connection failed: {e}")
        raise

    _create_indexes(_sync_db)


def close_mongo():
    """Close both clients. Call on app shutdown."""
    if _sync_client:
        _sync_client.close()
    if _async_client:
        _async_client.close()


def _create_indexes(db):
    """Ensure required indexes exist."""
    # users
    db.users.create_index("username", unique=True)

    # sessions
    db.user_sessions.create_index("token", unique=True)
    db.user_sessions.create_index("expires_at", expireAfterSeconds=0)  # TTL index

    # conversations
    db.conversations.create_index([("session_id", 1), ("created_at", 1)])

    # memories
    db.memories.create_index("key", unique=True)

    # action_logs
    db.action_logs.create_index("created_at")

    # tasks
    db.tasks.create_index("id", unique=True)

    logger.info("[MongoDB] Indexes created/verified.")


# ── Accessors ────────────────────────────────────────────────────────────────

def get_sync_db():
    """Return the synchronous PyMongo database handle."""
    if _sync_db is None:
        raise RuntimeError("MongoDB not initialised. Call init_mongo() first.")
    return _sync_db


def get_async_db() -> AsyncIOMotorDatabase:
    """Return the async Motor database handle."""
    if _async_db is None:
        raise RuntimeError("MongoDB not initialised. Call init_mongo() first.")
    return _async_db


# ── Health check ─────────────────────────────────────────────────────────────

def mongo_ping() -> dict:
    """Return a status dict — safe to call from /api/status."""
    try:
        db = get_sync_db()
        db.client.admin.command("ping")
        stats = db.command("dbStats")
        return {
            "status": "connected",
            "uri": settings.MONGODB_URI,
            "db": settings.MONGODB_DB,
            "collections": stats.get("collections", 0),
            "data_size_kb": round(stats.get("dataSize", 0) / 1024, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
