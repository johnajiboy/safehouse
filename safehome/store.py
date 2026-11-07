"""SQLite storage for cases, messages, the decision log and settings."""
from __future__ import annotations

import json
import sqlite3
from contextvars import ContextVar
from datetime import datetime

from . import config
from .models import Case

# The signed-in officer behind the current request, set by the API. Officer log entries record it.
current_officer: ContextVar[str | None] = ContextVar("current_officer", default=None)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    ref TEXT PRIMARY KEY,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_ref TEXT NOT NULL,
    kind TEXT NOT NULL,
    body TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL,
    case_ref TEXT,
    action TEXT NOT NULL,
    officer TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS officers (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(config.DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    # Databases made before officers were recorded in the log need the extra column.
    if "officer" not in {row["name"] for row in db.execute("PRAGMA table_info(log)")}:
        db.execute("ALTER TABLE log ADD COLUMN officer TEXT")
    return db


def reset() -> None:
    with connect() as db:
        for table in ("cases", "messages", "log", "settings"):
            db.execute(f"DELETE FROM {table}")


# --- Cases --------------------------------------------------------------------

def save_case(case: Case) -> None:
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO cases (ref, data) VALUES (?, ?)",
            (case.ref, json.dumps(case.to_dict())),
        )


def get_case(ref: str) -> Case | None:
    with connect() as db:
        row = db.execute("SELECT data FROM cases WHERE ref = ?", (ref,)).fetchone()
    return Case.from_dict(json.loads(row["data"])) if row else None


def all_cases() -> list[Case]:
    with connect() as db:
        rows = db.execute("SELECT data FROM cases").fetchall()
    return [Case.from_dict(json.loads(r["data"])) for r in rows]


def next_ref() -> str:
    with connect() as db:
        count = db.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
    return f"SH-{3001 + count}"


# --- Messages -----------------------------------------------------------------

def add_message(case_ref: str, kind: str, body: str, status: str) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        cursor = db.execute(
            "INSERT INTO messages (case_ref, kind, body, status, created_at, sent_at) VALUES (?, ?, ?, ?, ?, ?)",
            (case_ref, kind, body, status, now, now if status == "sent" else None),
        )
        return cursor.lastrowid


def messages_for(case_ref: str) -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM messages WHERE case_ref = ? ORDER BY id", (case_ref,)).fetchall()
    return [dict(r) for r in rows]


def get_message(message_id: int) -> dict | None:
    with connect() as db:
        row = db.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    return dict(row) if row else None


def mark_sent(message_id: int, body: str | None = None) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as db:
        if body is not None:
            db.execute("UPDATE messages SET body = ? WHERE id = ?", (body, message_id))
        db.execute("UPDATE messages SET status = 'sent', sent_at = ? WHERE id = ?", (now, message_id))


# --- Decision log ---------------------------------------------------------------

def log(actor: str, action: str, case_ref: str | None = None, officer: str | None = None) -> None:
    """Record a decision. Officer decisions also record which officer made them."""
    if actor == "Officer" and officer is None:
        officer = current_officer.get()
    with connect() as db:
        db.execute(
            "INSERT INTO log (at, actor, case_ref, action, officer) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), actor, case_ref, action, officer),
        )


def read_log(limit: int = 200) -> list[dict]:
    with connect() as db:
        rows = db.execute("SELECT * FROM log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# --- Settings -----------------------------------------------------------------

def get_setting(key: str, default):
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else default


def set_setting(key: str, value) -> None:
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, json.dumps(value)))
