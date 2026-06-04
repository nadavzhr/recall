"""Clipboard manipulation utilities for restoring data."""

import logging
from contextlib import contextmanager
from typing import Iterator

import pywintypes
import win32clipboard
import win32con

logger = logging.getLogger(__name__)


@contextmanager
def open_clipboard(hwnd: int | None = None) -> Iterator[None]:
    """Context manager for safely opening and closing the Windows clipboard."""
    opened = False
    try:
        win32clipboard.OpenClipboard(hwnd)  # type: ignore
        opened = True
        yield
    except pywintypes.error as e:
        logger.debug("Failed to open clipboard: %s", e)
        raise
    finally:
        if opened:
            try:
                win32clipboard.CloseClipboard()  # type: ignore
            except pywintypes.error as e:
                logger.debug("Failed to close clipboard: %s", e)


def set_clipboard_text(text: str) -> bool:
    """Put text back onto the Windows clipboard.

    Args:
        text: The string to place on the clipboard.

    Returns:
        True if successful, False otherwise.
    """
    try:
        with open_clipboard():
            win32clipboard.EmptyClipboard()  # type: ignore
            # CF_UNICODETEXT is the standard for modern Windows text
            win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)  # type: ignore
            return True
    except Exception as e:
        logger.error("Failed to set clipboard text: %s", e)
        return False


def simulate_paste() -> None:
    """Simulate a Ctrl+V keypress to paste the current clipboard contents."""
    import keyboard
    keyboard.send("ctrl+v")
