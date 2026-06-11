"""Database layer for BUPA Sync - supports SQLite (native) and PostgreSQL (Docker).

- Native/local development: SQLite (zero-config, file-based)
- Docker deployment: PostgreSQL (shared with n8n, concurrent access)

The DATABASE_URL environment variable controls which backend is used:
- Not set / empty: SQLite at backend/data/bupa_sync.db
- Set to postgresql://...: PostgreSQL
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

DATABASE_URL = os.environ.get("DATABASE_URL", "")
_USE_POSTGRES = DATABASE_URL.startswith("postgresql")

# SQLite path (only used when not using PostgreSQL)
DB_PATH = Path(__file__).parent / "data" / "bupa_sync.db"


def get_db_path() -> Path:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return DB_PATH


# --- Connection management ---


@contextmanager
def get_connection():
    """Get a database connection (SQLite or PostgreSQL)."""
    if _USE_POSTGRES:
        import psycopg2
        import psycopg2.extras

        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = False
        try:
            yield _PgConnectionWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(str(get_db_path()))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield _SqliteConnectionWrapper(conn)
            conn.commit()
        finally:
            conn.close()


class _SqliteConnectionWrapper:
    """Thin wrapper around sqlite3.Connection for unified interface."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query: str, params=None):
        if params:
            return self._conn.execute(query, params)
        return self._conn.execute(query)

    def executescript(self, script: str):
        self._conn.executescript(script)

    def fetchone(self, query: str, params=None) -> Optional[dict]:
        row = self.execute(query, params).fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params=None) -> list[dict]:
        rows = self.execute(query, params).fetchall()
        return [dict(row) for row in rows]


class _PgConnectionWrapper:
    """Thin wrapper around psycopg2 connection for unified interface."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, query: str, params=None):
        import psycopg2.extras

        # Convert ? placeholders to %s for psycopg2
        query = query.replace("?", "%s")
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur

    def executescript(self, script: str):
        """Execute a multi-statement script (adapted for PostgreSQL)."""
        # Convert SQLite-specific syntax to PostgreSQL
        script = script.replace("INSERT OR REPLACE", "INSERT")
        cur = self._conn.cursor()
        cur.execute(script)

    def fetchone(self, query: str, params=None) -> Optional[dict]:
        cur = self.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def fetchall(self, query: str, params=None) -> list[dict]:
        cur = self.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]


# --- Schema initialization ---

_SQLITE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT DEFAULT 'system'
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        action TEXT NOT NULL,
        category TEXT NOT NULL,
        user_id TEXT DEFAULT 'anonymous',
        user_name TEXT DEFAULT 'Anonymous',
        user_email TEXT DEFAULT '',
        details TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category);
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);

    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        user_email TEXT NOT NULL,
        access_token TEXT,
        refresh_token TEXT,
        groups TEXT DEFAULT '[]',
        expires_at TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS app_users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        given_name TEXT DEFAULT '',
        family_name TEXT DEFAULT '',
        groups TEXT DEFAULT '[]',
        first_login TEXT NOT NULL,
        last_login TEXT NOT NULL,
        login_count INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active'
    );
"""

_POSTGRES_SCHEMA = """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT DEFAULT 'system'
    );

    CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        action TEXT NOT NULL,
        category TEXT NOT NULL,
        user_id TEXT DEFAULT 'anonymous',
        user_name TEXT DEFAULT 'Anonymous',
        user_email TEXT DEFAULT '',
        details TEXT DEFAULT '{}',
        metadata TEXT DEFAULT '{}'
    );

    CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp DESC);
    CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_log(category);
    CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);

    CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        user_email TEXT NOT NULL,
        access_token TEXT,
        refresh_token TEXT,
        groups TEXT DEFAULT '[]',
        expires_at TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS app_users (
        user_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL DEFAULT '',
        given_name TEXT DEFAULT '',
        family_name TEXT DEFAULT '',
        groups TEXT DEFAULT '[]',
        first_login TEXT NOT NULL,
        last_login TEXT NOT NULL,
        login_count INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active'
    );
"""


def init_db():
    """Initialize database tables."""
    with get_connection() as conn:
        if _USE_POSTGRES:
            conn.executescript(_POSTGRES_SCHEMA)
            # Migration: add groups column if missing
            try:
                conn.execute(
                    "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS groups TEXT DEFAULT '[]'"
                )
            except Exception:
                pass
        else:
            conn.executescript(_SQLITE_SCHEMA)


# --- Settings ---
def get_setting(key: str, default: str = "") -> str:
    with get_connection() as conn:
        row = conn.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default


def set_setting(key: str, value: str, user: str = "system"):
    with get_connection() as conn:
        if _USE_POSTGRES:
            conn.execute(
                "INSERT INTO settings (key, value, updated_at, updated_by) "
                "VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, "
                "updated_at = EXCLUDED.updated_at, updated_by = EXCLUDED.updated_by",
                (key, value, datetime.now(timezone.utc).isoformat(), user),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?)",
                (key, value, datetime.now(timezone.utc).isoformat(), user),
            )


def get_all_settings() -> dict:
    with get_connection() as conn:
        rows = conn.fetchall("SELECT key, value FROM settings")
        return {row["key"]: row["value"] for row in rows}


# --- Audit ---
def log_audit_event(
    action: str,
    category: str,
    user_id: str = "anonymous",
    user_name: str = "Anonymous",
    user_email: str = "",
    details: Optional[dict] = None,
    metadata: Optional[dict] = None,
) -> dict:
    event_id = f"evt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    timestamp = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO audit_log (id, timestamp, action, category, user_id, user_name, user_email, details, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event_id,
                timestamp,
                action,
                category,
                user_id,
                user_name,
                user_email,
                json.dumps(details or {}),
                json.dumps(metadata or {}),
            ),
        )
    return {
        "id": event_id,
        "timestamp": timestamp,
        "action": action,
        "category": category,
        "user_id": user_id,
        "user_name": user_name,
        "details": details or {},
    }


def get_audit_events(
    limit: int = 100, category: Optional[str] = None, user_id: Optional[str] = None
) -> list[dict]:
    with get_connection() as conn:
        if _USE_POSTGRES:
            query = "SELECT * FROM audit_log"
            params: list = []
            conditions: list[str] = []
            if category:
                conditions.append("category = %s")
                params.append(category)
            if user_id:
                conditions.append("user_id = %s")
                params.append(user_id)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp DESC LIMIT %s"
            params.append(limit)
            rows = conn.fetchall(query, params)
        else:
            query = "SELECT * FROM audit_log"
            params = []
            conditions = []
            if category:
                conditions.append("category = ?")
                params.append(category)
            if user_id:
                conditions.append("user_id = ?")
                params.append(user_id)
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            rows = conn.fetchall(query, params)

        return [
            {
                **row,
                "details": json.loads(row["details"])
                if isinstance(row["details"], str)
                else row["details"],
                "metadata": json.loads(row["metadata"])
                if isinstance(row["metadata"], str)
                else row["metadata"],
            }
            for row in rows
        ]


# --- Sessions ---
def create_session(
    session_id: str,
    user_id: str,
    user_name: str,
    user_email: str,
    access_token: str = "",
    refresh_token: str = "",
    groups: str = "[]",
    expires_at: str = "",
):
    with get_connection() as conn:
        if _USE_POSTGRES:
            conn.execute(
                "INSERT INTO sessions (session_id, user_id, user_name, user_email, access_token, refresh_token, groups, expires_at, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (session_id) DO UPDATE SET "
                "user_id = EXCLUDED.user_id, user_name = EXCLUDED.user_name, "
                "user_email = EXCLUDED.user_email, access_token = EXCLUDED.access_token, "
                "refresh_token = EXCLUDED.refresh_token, groups = EXCLUDED.groups, expires_at = EXCLUDED.expires_at",
                (
                    session_id,
                    user_id,
                    user_name,
                    user_email,
                    access_token,
                    refresh_token,
                    groups,
                    expires_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, user_id, user_name, user_email, access_token, refresh_token, groups, expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    user_id,
                    user_name,
                    user_email,
                    access_token,
                    refresh_token,
                    groups,
                    expires_at,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def get_session(session_id: str) -> Optional[dict]:
    with get_connection() as conn:
        return conn.fetchone(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        )


def delete_session(session_id: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


# --- App Users (auto-created on IAS login) ---


def upsert_app_user(
    user_id: str,
    display_name: str,
    email: str = "",
    given_name: str = "",
    family_name: str = "",
    groups: str = "[]",
):
    """Create or update an app user record on login."""
    now = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        if _USE_POSTGRES:
            conn.execute(
                """INSERT INTO app_users (user_id, display_name, email, given_name, family_name, groups, first_login, last_login, login_count, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 'active')
                ON CONFLICT (user_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    email = EXCLUDED.email,
                    given_name = EXCLUDED.given_name,
                    family_name = EXCLUDED.family_name,
                    groups = EXCLUDED.groups,
                    last_login = EXCLUDED.last_login,
                    login_count = app_users.login_count + 1""",
                (
                    user_id,
                    display_name,
                    email,
                    given_name,
                    family_name,
                    groups,
                    now,
                    now,
                ),
            )
        else:
            existing = conn.fetchone(
                "SELECT * FROM app_users WHERE user_id = ?", (user_id,)
            )
            if existing:
                conn.execute(
                    """UPDATE app_users SET display_name=?, email=?, given_name=?, family_name=?,
                       groups=?, last_login=?, login_count=login_count+1 WHERE user_id=?""",
                    (
                        display_name,
                        email,
                        given_name,
                        family_name,
                        groups,
                        now,
                        user_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO app_users (user_id, display_name, email, given_name, family_name, groups, first_login, last_login, login_count, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'active')""",
                    (
                        user_id,
                        display_name,
                        email,
                        given_name,
                        family_name,
                        groups,
                        now,
                        now,
                    ),
                )


def list_app_users() -> list[dict]:
    """Return all registered app users."""
    with get_connection() as conn:
        return conn.fetchall("SELECT * FROM app_users ORDER BY last_login DESC")


def get_app_user(user_id: str) -> Optional[dict]:
    """Get a specific app user."""
    with get_connection() as conn:
        return conn.fetchone("SELECT * FROM app_users WHERE user_id = ?", (user_id,))


# Initialize on import
init_db()
