"""SQLite database — synchronous for Streamlit."""

import sqlite3
import hashlib
import secrets
import os

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


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"


def verify_password(password: str, stored: str) -> bool:
    salt, hashed = stored.split("$", 1)
    return hashlib.sha256((salt + password).encode()).hexdigest() == hashed


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


def create_user(email, name, password_hash, role="user", ah_registered_user_id="", ah_tool_pack_id="", company="") -> dict:
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
