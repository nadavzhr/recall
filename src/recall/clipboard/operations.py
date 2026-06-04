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


def set_clipboard_image(image_bytes: bytes) -> bool:
    """Put an image back onto the Windows clipboard.
    
    Args:
        image_bytes: PNG or other image bytes.
        
    Returns:
        True if successful, False otherwise.
    """
    from PIL import Image
    import io
    
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Windows clipboard needs a DIB. We can use io.BytesIO and save as BMP.
        output = io.BytesIO()
        img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:] # The BMP file header is 14 bytes
        
        with open_clipboard():
            win32clipboard.EmptyClipboard()  # type: ignore
            win32clipboard.SetClipboardData(win32con.CF_DIB, data)  # type: ignore
            return True
    except Exception as e:
        logger.error("Failed to set clipboard image: %s", e)
        return False


def simulate_paste() -> None:
    """Simulate a Ctrl+V keypress to paste the current clipboard contents."""
    import keyboard
    keyboard.send("ctrl+v")
