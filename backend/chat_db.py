"""
chat_db.py — thin SQLite helper for persisting chat sessions and messages.

WHY sqlite3 instead of SQLAlchemy:
    SQLAlchemy is powerful but brings ORM overhead (session lifecycle, model
    declaration, migrations) that we simply don't need for two tiny tables.
    The stdlib sqlite3 module is zero-dependency, perfectly sufficient for a
    local MVP, and keeps this module readable at a glance.
"""

import sqlite3
from pathlib import Path
from typing import Optional

# Resolve the DB path relative to THIS file so it works regardless of where
# uvicorn is invoked from (e.g., `cd backend && uvicorn main:app` vs running
# from the repo root).
DB_PATH = Path(__file__).parent / "myuoft.db"


def _get_conn() -> sqlite3.Connection:
    """
    Open a fresh connection for each call.

    WHY not a module-level connection:
        sqlite3 connections are not thread-safe by default.  FastAPI runs
        async handlers in a thread pool, so sharing one connection across
        requests risks data corruption.  Opening per-call is slightly slower
        but safe without needing connection-pool machinery.
    """
    conn = sqlite3.connect(DB_PATH)
    # Return rows as dicts so callers can do row["id"] instead of row[0].
    conn.row_factory = sqlite3.Row
    # ON DELETE CASCADE requires foreign-key enforcement to be turned on
    # explicitly in SQLite — it is off by default for backwards compat.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """
    Create tables if they don't exist.

    WHY CREATE TABLE IF NOT EXISTS:
        This makes init_db() idempotent — safe to call on every app startup
        without wiping existing data or raising errors on a fresh database.
    """
    conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                title      TEXT    NOT NULL DEFAULT 'New Chat',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL
                               REFERENCES chat_sessions(id) ON DELETE CASCADE,
                role       TEXT    NOT NULL,   -- 'user' or 'assistant'
                content    TEXT    NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
    finally:
        conn.close()


def create_session(title: str = "New Chat") -> dict:
    """
    Insert a new chat session row and return it as a plain dict.

    Returns: { id, title, created_at }
    """
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_sessions (title) VALUES (?)", (title,)
        )
        conn.commit()
        # Fetch the freshly inserted row so we get the DB-generated created_at.
        row = conn.execute(
            "SELECT id, title, created_at FROM chat_sessions WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def list_sessions() -> list[dict]:
    """
    Return all sessions newest-first, each with a message_count field.

    WHY include message_count in the list query:
        The sidebar needs to show something useful about each session without
        a second round-trip per row.  A single LEFT JOIN is cheaper than N+1
        calls to get_messages() for each session.
    """
    conn = _get_conn()
    try:
        rows = conn.execute("""
            SELECT
                s.id,
                s.title,
                s.created_at,
                COUNT(m.id) AS message_count
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON m.session_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_messages(session_id: int) -> list[dict]:
    """
    Return all messages for a session in chronological order.

    Returns: [{ id, role, content }, ...]
    WHY id is included: the frontend needs a stable identifier per message to
    support editing — when a user edits a past message, we have to tell the
    DB exactly which row (and everything after it) to discard. Array index
    isn't reliable for that once messages have been through DB storage/reload.
    """
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT id, role, content FROM chat_messages WHERE session_id = ? ORDER BY id ASC",
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def save_message(session_id: int, role: str, content: str) -> int:
    """Insert one message into the session and return its new id."""
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "INSERT INTO chat_messages (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def delete_messages_from(session_id: int, message_id: int) -> None:
    """
    Delete a message and every message after it (by id) within one session.

    WHY this exists: editing a past message means the conversation branches —
    the old reply (and anything the user sent after it) no longer applies to
    the corrected message. Rather than support multiple branches (real
    complexity for no payoff in a single-user local MVP), we just discard the
    old tail and let the edited message start a fresh one, matching how
    ChatGPT-style "edit and resend" works.

    WHY id >= message_id, not created_at: CURRENT_TIMESTAMP has whole-second
    resolution, so a user message and its assistant reply (saved a moment
    apart) can tie on created_at. The autoincrement id has no such collision
    and is strictly ordered, so it's the only reliable "from here on" cutoff.
    """
    conn = _get_conn()
    try:
        conn.execute(
            "DELETE FROM chat_messages WHERE session_id = ? AND id >= ?",
            (session_id, message_id),
        )
        conn.commit()
    finally:
        conn.close()


def update_session_title(session_id: int, title: str) -> None:
    """
    Overwrite a session's title.

    WHY this exists:
        When a session is created we don't know the topic yet, so it starts as
        "New Chat".  After the first user message arrives we call this to set
        the title to a truncated snippet of that message — giving the sidebar
        meaningful labels without a separate naming step.
    """
    conn = _get_conn()
    try:
        conn.execute(
            "UPDATE chat_sessions SET title = ? WHERE id = ?",
            (title, session_id),
        )
        conn.commit()
    finally:
        conn.close()
