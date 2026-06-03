"""Utility functions for Project Recall."""

from __future__ import annotations

TRUNCATE_LIMIT = 75

def truncate_text(text: str, limit: int = TRUNCATE_LIMIT) -> str:
    """Return a clipped preview of the text for logging."""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def preview_text(text: str | None, limit: int = 50) -> str:
    """Return a safe preview for optional text values."""
    if not text:
        return "<empty>"
    return truncate_text(text, limit=limit)
