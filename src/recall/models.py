"""Common data models for Project Recall."""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Command(str, Enum):
    """Commands sent to the UI from background processes."""
    SHOW_GUI = "SHOW_GUI"

@dataclass(frozen=True, slots=True)
class ClipboardEntry:
    """Represents a single clipboard history entry in the database."""
    item_id: int
    content_type: str
    content_text: str | None
    content_data: bytes | None
    timestamp: datetime

@dataclass(frozen=True)
class ClipboardEvent:
    """Event data sent through the update queue from the listener."""
    content_type: str
    content_text: str | None = None
    content_data: bytes | None = None
