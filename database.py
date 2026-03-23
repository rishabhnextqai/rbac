"""
Database layer — auto-selects backend:
  - If SUPABASE_URL is set → uses Supabase (persistent, production)
  - Otherwise → uses local SQLite (ephemeral on Streamlit Cloud)
"""

import hashlib
import secrets
import os

try:
    import streamlit as st
    def _get_secret(key, default=""):
        try:
            return st.secrets[key]
        except Exception:
            return os.getenv(key, default)
except ImportError:
    def _get_secret(key, default=""):
        return os.getenv(key, default)

SUPABASE_URL = _get_secret("SUPABASE_URL")
SUPABASE_KEY = _get_secret("SUPABASE_KEY")

USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

# ══════════════════════════════════════════════════════════════
#  Password utilities (shared by both backends)
# ══════════════════════════════════════════════════════════════

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, hashed = stored.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


# ══════════════════════════════════════════════════════════════
#  Supabase backend
# ══════════════════════════════════════════════════════════════

if USE_SUPABASE:
    import httpx

    _headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    _base = f"{SUPABASE_URL}/rest/v1/users"

    def init_db():
        """Supabase table must be created via the dashboard or SQL editor:
        CREATE TABLE users (
            id BIGSERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            ah_registered_user_id TEXT DEFAULT '',
            ah_tool_pack_id TEXT DEFAULT '',
            company TEXT DEFAULT '',
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        ALTER TABLE users ENABLE ROW LEVEL SECURITY;
        CREATE POLICY "service_role_all" ON users FOR ALL USING (true);
        """
        pass  # Table created via Supabase dashboard

    def get_user_by_email(email: str) -> dict | None:
        r = httpx.get(f"{_base}?email=eq.{email}&limit=1", headers=_headers)
        rows = r.json()
        return rows[0] if rows else None

    def get_user_by_id(user_id: int) -> dict | None:
        r = httpx.get(f"{_base}?id=eq.{user_id}&limit=1", headers=_headers)
        rows = r.json()
        return rows[0] if rows else None

    def create_user(email, name, password_hash, role="user", ah_registered_user_id="",
                    ah_tool_pack_id="", company="") -> dict:
        body = {
            "email": email, "name": name, "password_hash": password_hash,
            "role": role, "ah_registered_user_id": ah_registered_user_id,
            "ah_tool_pack_id": ah_tool_pack_id, "company": company,
        }
        r = httpx.post(_base, json=body, headers=_headers)
        r.raise_for_status()
        return r.json()[0]

    def list_users() -> list[dict]:
        r = httpx.get(f"{_base}?order=created_at.desc", headers=_headers)
        return r.json()

    def update_user(user_id: int, **fields) -> dict | None:
        if not fields:
            return get_user_by_id(user_id)
        r = httpx.patch(f"{_base}?id=eq.{user_id}", json=fields, headers=_headers)
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else get_user_by_id(user_id)

    def delete_user(user_id: int) -> bool:
        r = httpx.delete(f"{_base}?id=eq.{user_id}", headers=_headers)
        return r.status_code < 300

    def seed_admin(email, name, password, ah_tool_pack_id="", ah_registered_user_id=""):
        if not get_user_by_email(email):
            create_user(
                email=email, name=name, password_hash=hash_password(password),
                role="admin", ah_registered_user_id=ah_registered_user_id,
                ah_tool_pack_id=ah_tool_pack_id, company="Next Quarter",
            )


# ══════════════════════════════════════════════════════════════
#  SQLite backend (local dev / fallback)
# ══════════════════════════════════════════════════════════════

else:
    import sqlite3

    DB_PATH = os.path.join(os.path.dirname(__file__), "app.db")

    def _dict_row(cursor, row):
        return {col[0]: row[i] for i, col in enumerate(cursor.description)}

    def get_db():
        db = sqlite3.connect(DB_PATH)
        db.row_factory = _dict_row
        return db

    def init_db():
        db = get_db()
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                ah_registered_user_id TEXT DEFAULT '',
                ah_tool_pack_id TEXT DEFAULT '',
                company TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()
        db.close()

    def get_user_by_email(email: str) -> dict | None:
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        db.close()
        return row

    def get_user_by_id(user_id: int) -> dict | None:
        db = get_db()
        row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        db.close()
        return row

    def create_user(email, name, password_hash, role="user", ah_registered_user_id="",
                    ah_tool_pack_id="", company="") -> dict:
        db = get_db()
        cursor = db.execute(
            "INSERT INTO users (email, name, password_hash, role, ah_registered_user_id, ah_tool_pack_id, company) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (email, name, password_hash, role, ah_registered_user_id, ah_tool_pack_id, company),
        )
        db.commit()
        user_id = cursor.lastrowid
        db.close()
        return get_user_by_id(user_id)

    def list_users() -> list[dict]:
        db = get_db()
        rows = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        db.close()
        return rows

    def update_user(user_id: int, **fields) -> dict | None:
        if not fields:
            return get_user_by_id(user_id)
        set_clause = ", ".join(f"{k} = ?" for k in fields.keys())
        values = list(fields.values()) + [user_id]
        db = get_db()
        db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
        db.commit()
        db.close()
        return get_user_by_id(user_id)

    def delete_user(user_id: int) -> bool:
        db = get_db()
        cursor = db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()
        deleted = cursor.rowcount > 0
        db.close()
        return deleted

    def seed_admin(email, name, password, ah_tool_pack_id="", ah_registered_user_id=""):
        if not get_user_by_email(email):
            create_user(
                email=email, name=name, password_hash=hash_password(password),
                role="admin", ah_registered_user_id=ah_registered_user_id,
                ah_tool_pack_id=ah_tool_pack_id, company="Next Quarter",
            )
