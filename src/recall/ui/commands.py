"""UI specific commands and events."""

from enum import Enum

class Command(str, Enum):
    """Commands sent to the UI from background processes."""
    SHOW_GUI = "SHOW_GUI"
