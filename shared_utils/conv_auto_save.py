"""
Conversation Auto-Save Hook - Integrates conversation_store into the chat flow.

This module provides hooks that can be called from bridge_all.py's predict()
to automatically save conversations without modifying existing UI code.
"""

import time
from typing import List, Optional
from loguru import logger

try:
    from .conversation_store import (
        create_conversation,
        save_message,
        save_messages_batch,
        get_messages,
        get_conversation,
        list_conversations,
        delete_conversation,
        update_conversation_title,
        auto_title_from_content,
        export_conversation_markdown,
    )
    STORE_AVAILABLE = True
except ImportError:
    STORE_AVAILABLE = False
    logger.warning("conversation_store not available, auto-save disabled")


# Global state: current conversation ID
_current_conv_id: Optional[str] = None
_current_model: str = "unknown"


def get_current_conv_id() -> Optional[str]:
    return _current_conv_id


def start_conversation(model: str = "unknown", title: str = None) -> str:
    """Start a new conversation and return its ID."""
    global _current_conv_id, _current_model
    if not STORE_AVAILABLE:
        return None

    try:
        _current_conv_id = create_conversation(
            title=title or "New Conversation",
            model=model,
        )
        _current_model = model
        logger.info(f"Started conversation: {_current_conv_id}")
        return _current_conv_id
    except Exception as e:
        logger.error(f"Failed to start conversation: {e}")
        return None


def save_user_message(content: str, token_count: int = 0):
    """Save a user message to the current conversation."""
    if not STORE_AVAILABLE or not _current_conv_id:
        return
    try:
        save_message(_current_conv_id, "user", content, token_count)
        # Auto-title from first message
        conv = get_conversation(_current_conv_id)
        if conv and conv["title"] == "New Conversation" and conv["message_count"] <= 2:
            auto_title_from_content(_current_conv_id)
    except Exception as e:
        logger.error(f"Failed to save user message: {e}")


def save_assistant_message(content: str, token_count: int = 0):
    """Save an assistant message to the current conversation."""
    if not STORE_AVAILABLE or not _current_conv_id:
        return
    try:
        save_message(_current_conv_id, "assistant", content, token_count)
    except Exception as e:
        logger.error(f"Failed to save assistant message: {e}")


def load_conversation_messages(conv_id: str) -> List[dict]:
    """Load messages from a saved conversation."""
    if not STORE_AVAILABLE:
        return []
    global _current_conv_id
    _current_conv_id = conv_id
    try:
        return get_messages(conv_id)
    except Exception as e:
        logger.error(f"Failed to load conversation: {e}")
        return []


def get_saved_conversations(limit: int = 50, search: str = None) -> List[dict]:
    """Get list of saved conversations."""
    if not STORE_AVAILABLE:
        return []
    try:
        return list_conversations(limit=limit, search=search)
    except Exception as e:
        logger.error(f"Failed to list conversations: {e}")
        return []


def export_current_conversation() -> str:
    """Export current conversation as Markdown."""
    if not STORE_AVAILABLE or not _current_conv_id:
        return ""
    try:
        return export_conversation_markdown(_current_conv_id)
    except Exception as e:
        logger.error(f"Failed to export conversation: {e}")
        return ""


def delete_current_conversation():
    """Delete the current conversation."""
    global _current_conv_id
    if not STORE_AVAILABLE or not _current_conv_id:
        return
    try:
        delete_conversation(_current_conv_id)
        _current_conv_id = None
    except Exception as e:
        logger.error(f"Failed to delete conversation: {e}")
