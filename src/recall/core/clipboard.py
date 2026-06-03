"""Clipboard manipulation utilities for restoring data."""

import logging
import win32clipboard
import win32con

logger = logging.getLogger(__name__)


def set_clipboard_text(text: str) -> bool:
    """Put text back onto the Windows clipboard.

    Args:
        text: The string to place on the clipboard.

    Returns:
        True if successful, False otherwise.
    """
    clipboard_open = False
    try:
        win32clipboard.OpenClipboard()  # type: ignore
        clipboard_open = True
        win32clipboard.EmptyClipboard()  # type: ignore
        # CF_UNICODETEXT is the standard for modern Windows text
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)  # type: ignore
        return True
    except Exception as e:
        logger.error("Failed to set clipboard text: %s", e)
        return False
    finally:
        if clipboard_open:
            try:
                win32clipboard.CloseClipboard()  # type: ignore
            except Exception:
                pass


def simulate_paste() -> None:
    """Simulate a Ctrl+V keypress to paste the current clipboard contents."""
    import keyboard
    keyboard.send("ctrl+v")
