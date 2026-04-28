"""
Conversation Store - SQLite-backed conversation persistence.

Features:
- Save/load/delete conversations
- List all saved conversations with metadata
- Search conversations by content
- Auto-save on conversation end
- Export to Markdown
"""

import sqlite3
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from loguru import logger


DB_PATH = Path(__file__).parent.parent / "conversations.db"


def _get_db() -> sqlite3.Connection:
    """Get a database connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Initialize the conversation database schema."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Conversation',
            model TEXT NOT NULL DEFAULT 'unknown',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            tags TEXT DEFAULT '[]',
            is_pinned INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            timestamp REAL NOT NULL,
            token_count INTEGER DEFAULT 0,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv_id
            ON messages(conversation_id, id);

        CREATE INDEX IF NOT EXISTS idx_messages_search
            ON messages(conversation_id, content);

        CREATE INDEX IF NOT EXISTS idx_conversations_updated
            ON conversations(updated_at DESC);
    """)
    conn.commit()
    conn.close()


# Auto-init on import
try:
    init_db()
except Exception as e:
    logger.warning(f"Failed to init conversation DB: {e}")


# ─── CRUD Operations ────────────────────────────────────

def create_conversation(
    title: str = "New Conversation",
    model: str = "unknown",
    tags: List[str] = None,
) -> str:
    """Create a new conversation, returns conversation ID."""
    conv_id = f"conv_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
    now = time.time()
    conn = _get_db()
    conn.execute(
        """INSERT INTO conversations (id, title, model, created_at, updated_at, tags)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (conv_id, title, model, now, now, json.dumps(tags or [])),
    )
    conn.commit()
    conn.close()
    return conv_id


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    token_count: int = 0,
) -> int:
    """Save a single message to a conversation. Returns message row id."""
    conn = _get_db()
    cursor = conn.execute(
        """INSERT INTO messages (conversation_id, role, content, timestamp, token_count)
           VALUES (?, ?, ?, ?, ?)""",
        (conversation_id, role, content, time.time(), token_count),
    )
    msg_id = cursor.lastrowid

    # Update conversation metadata
    conn.execute(
        """UPDATE conversations
           SET updated_at = ?,
               message_count = (SELECT COUNT(*) FROM messages WHERE conversation_id = ?),
               total_tokens = total_tokens + ?
           WHERE id = ?""",
        (time.time(), conversation_id, token_count, conversation_id),
    )
    conn.commit()
    conn.close()
    return msg_id


def save_messages_batch(
    conversation_id: str,
    messages: List[Dict[str, any]],
) -> None:
    """Save multiple messages at once (for import/restore)."""
    conn = _get_db()
    now = time.time()
    total_tokens = 0
    for msg in messages:
        conn.execute(
            """INSERT INTO messages (conversation_id, role, content, timestamp, token_count)
               VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, msg["role"], msg["content"], now, msg.get("token_count", 0)),
        )
        total_tokens += msg.get("token_count", 0)

    conn.execute(
        """UPDATE conversations
           SET updated_at = ?,
               message_count = (SELECT COUNT(*) FROM messages WHERE conversation_id = ?),
               total_tokens = total_tokens + ?
           WHERE id = ?""",
        (now, conversation_id, total_tokens, conversation_id),
    )
    conn.commit()
    conn.close()


def get_messages(conversation_id: str) -> List[Dict[str, any]]:
    """Get all messages for a conversation, ordered chronologically."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT role, content, timestamp, token_count
           FROM messages
           WHERE conversation_id = ?
           ORDER BY id ASC""",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conversation_id: str) -> Optional[Dict]:
    """Get conversation metadata."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    conn.close()
    if row:
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        return d
    return None


def list_conversations(
    limit: int = 50,
    offset: int = 0,
    search: str = None,
) -> List[Dict]:
    """List conversations, newest first. Optionally search by title/content."""
    conn = _get_db()
    if search:
        rows = conn.execute(
            """SELECT DISTINCT c.* FROM conversations c
               LEFT JOIN messages m ON c.id = m.conversation_id
               WHERE c.title LIKE ? OR m.content LIKE ?
               ORDER BY c.is_pinned DESC, c.updated_at DESC
               LIMIT ? OFFSET ?""",
            (f"%{search}%", f"%{search}%", limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM conversations
               ORDER BY is_pinned DESC, updated_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ).fetchall()
    conn.close()
    result = []
    for row in rows:
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        d["created_at_str"] = datetime.fromtimestamp(d["created_at"]).strftime("%Y-%m-%d %H:%M")
        d["updated_at_str"] = datetime.fromtimestamp(d["updated_at"]).strftime("%Y-%m-%d %H:%M")
        result.append(d)
    return result


def update_conversation_title(conversation_id: str, title: str):
    """Update conversation title."""
    conn = _get_db()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, time.time(), conversation_id),
    )
    conn.commit()
    conn.close()


def update_conversation_model(conversation_id: str, model: str):
    """Update the model used for this conversation."""
    conn = _get_db()
    conn.execute(
        "UPDATE conversations SET model = ?, updated_at = ? WHERE id = ?",
        (model, time.time(), conversation_id),
    )
    conn.commit()
    conn.close()


def toggle_pin(conversation_id: str) -> bool:
    """Toggle pinned status, returns new state."""
    conn = _get_db()
    row = conn.execute(
        "SELECT is_pinned FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if row:
        new_state = 1 if row["is_pinned"] == 0 else 0
        conn.execute(
            "UPDATE conversations SET is_pinned = ? WHERE id = ?",
            (new_state, conversation_id),
        )
        conn.commit()
        conn.close()
        return bool(new_state)
    conn.close()
    return False


def delete_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    conn = _get_db()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
    conn.close()


def get_conversation_count() -> int:
    """Get total number of conversations."""
    conn = _get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM conversations").fetchone()
    conn.close()
    return row["cnt"]


def export_conversation_markdown(conversation_id: str) -> str:
    """Export a conversation to Markdown format."""
    conv = get_conversation(conversation_id)
    if not conv:
        return ""

    messages = get_messages(conversation_id)
    md = f"# {conv['title']}\n\n"
    md += f"- **Model**: {conv['model']}\n"
    md += f"- **Created**: {conv['created_at_str']}\n"
    md += f"- **Messages**: {conv['message_count']}\n"
    md += f"- **Total tokens**: {conv['total_tokens']}\n\n"
    md += "---\n\n"

    for msg in messages:
        role_icon = "🧑" if msg["role"] == "user" else "🤖" if msg["role"] == "assistant" else "⚙️"
        md += f"### {role_icon} {msg['role'].capitalize()}\n\n"
        md += f"{msg['content']}\n\n"

    return md


def search_messages(query: str, limit: int = 20) -> List[Dict]:
    """Full-text search across all messages."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT m.*, c.title as conv_title
           FROM messages m
           JOIN conversations c ON m.conversation_id = c.id
           WHERE m.content LIKE ?
           ORDER BY m.timestamp DESC
           LIMIT ?""",
        (f"%{query}%", limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def auto_title_from_content(conversation_id: str) -> str:
    """Generate a title from the first user message."""
    messages = get_messages(conversation_id)
    for msg in messages:
        if msg["role"] == "user":
            # Use first 50 chars of first user message as title
            title = msg["content"].strip()[:50]
            if len(msg["content"]) > 50:
                title += "..."
            update_conversation_title(conversation_id, title)
            return title
    return "New Conversation"
