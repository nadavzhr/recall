"""Windows clipboard listener for multi-format updates."""

import ctypes
import threading
import logging
import hashlib
from dataclasses import dataclass
from queue import Queue
from typing import Callable

import pywintypes
import win32api
import win32clipboard
import win32con
import win32gui

from recall.models import ClipboardEvent
from recall.ui.commands import Command
from recall.clipboard.operations import open_clipboard

logger = logging.getLogger(__name__)

ERROR_CLASS_ALREADY_EXISTS = 1410
WM_CLIPBOARDUPDATE = 0x031D
WINDOW_CLASS_NAME = "ProjectRecallListener"
WINDOW_TITLE = "RecallHiddenWindow"

user32 = ctypes.windll.user32

def add_clipboard_listener(hwnd: int) -> bool:
    return bool(user32.AddClipboardFormatListener(hwnd))

def remove_clipboard_listener(hwnd: int) -> None:
    user32.RemoveClipboardFormatListener(hwnd)

def unregister_hotkey(hwnd: int, hotkey_id: int) -> None:
    user32.UnregisterHotKey(hwnd, hotkey_id)

@dataclass
class ListenerState:
    thread: threading.Thread | None = None
    last_content_hash: bytes | None = None
    hotkey_id: int = 1


class Win32MessageWindow:
    """A hidden window that acts as a message pump for Win32 events."""
    
    def __init__(self, on_clipboard_update: Callable[[], None], on_hotkey: Callable[[int], None], hotkey_id: int):
        self._on_clipboard_update = on_clipboard_update
        self._on_hotkey = on_hotkey
        self._hotkey_id = hotkey_id
        self.hwnd: int | None = None

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Handle Win32 messages."""
        if msg == WM_CLIPBOARDUPDATE:
            self._on_clipboard_update()
            return 0

        if msg == win32con.WM_HOTKEY:
            self._on_hotkey(wparam)
            return 0

        if msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0

        if msg == win32con.WM_DESTROY:
            unregister_hotkey(hwnd, self._hotkey_id)
            remove_clipboard_listener(hwnd)
            self.hwnd = None
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def create_and_pump(self) -> None:
        wc = win32gui.WNDCLASS()
        wc.lpfnWndProc = self._wndproc  # type: ignore[assignment]
        wc.lpszClassName = WINDOW_CLASS_NAME  # type: ignore[assignment]
        wc.hInstance = win32api.GetModuleHandle(None)  # type: ignore[assignment]

        try:
            win32gui.RegisterClass(wc)
        except win32gui.error as exc:
            if getattr(exc, "winerror", None) != ERROR_CLASS_ALREADY_EXISTS:
                logger.error("Failed to register window class: %s", exc)
                return

        self.hwnd = win32gui.CreateWindowEx(  # type: ignore
            0, WINDOW_CLASS_NAME, WINDOW_TITLE,
            0, 0, 0, 0, 0,
            win32con.HWND_MESSAGE,
            0, wc.hInstance, None
        )

        if not self.hwnd:
            logger.error("Failed to create message window")
            return

        if not add_clipboard_listener(self.hwnd):
            win32gui.DestroyWindow(self.hwnd)  # type: ignore
            self.hwnd = None
            logger.error("Failed to add clipboard format listener")
            return

        win32gui.PumpMessages()

    def destroy(self) -> None:
        if self.hwnd:
            win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)


class ClipboardListener:
    """Listen for clipboard updates in a background thread and queue events."""

    def __init__(self, event_queue: Queue[ClipboardEvent], command_queue: Queue[Command] | None = None) -> None:
        """Create a clipboard listener.

        Args:
            event_queue: Thread-safe queue where updates are posted.
            command_queue: Optional queue to send application commands (e.g., hotkey triggers).
        """
        self._queue = event_queue
        self._command_queue = command_queue
        self._state = ListenerState()
        self._window: Win32MessageWindow | None = None

    def _handle_text(self, text: str) -> None:
        """Process text clipboard content."""
        content_hash = hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()
        if content_hash != self._state.last_content_hash:
            self._state.last_content_hash = content_hash
            self._queue.put(ClipboardEvent(content_type="text", content_text=text))

    def _handle_image(self) -> None:
        """Process image clipboard content."""
        from PIL import ImageGrab, Image
        import io
        try:
            img = ImageGrab.grabclipboard()
            if isinstance(img, Image.Image):
                # Convert to bytes (PNG)
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                full_bytes = img_byte_arr.getvalue()
                
                content_hash = hashlib.blake2b(full_bytes, digest_size=16).digest()
                if content_hash != self._state.last_content_hash:
                    self._state.last_content_hash = content_hash
                    
                    # Create thumbnail
                    img.thumbnail((250, 250))
                    thumb_byte_arr = io.BytesIO()
                    img.save(thumb_byte_arr, format='PNG')
                    thumb_bytes = thumb_byte_arr.getvalue()
                    
                    self._queue.put(ClipboardEvent(
                        content_type="image",
                        content_data=full_bytes,
                        thumbnail_data=thumb_bytes
                    ))
        except Exception as e:
            logger.debug("Failed to grab image from clipboard: %s", e)

    def _process_update(self) -> None:
        """Inspect the clipboard and queue events for supported formats."""
        has_text = False
        has_image = False
        text = None

        try:
            with open_clipboard():
                # 1. Handle Text
                if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                    text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)  # type: ignore
                    has_text = True
                # 2. Handle Images
                elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                    has_image = True
        except pywintypes.error as e:
            logger.debug("Clipboard access error: %s", e)
            return

        if has_text and text is not None:
            self._handle_text(text)
        elif has_image:
            self._handle_image()

    def _on_hotkey(self, wparam: int) -> None:
        logger.info("WM_HOTKEY received! wparam: %s, hotkey_id: %s", wparam, self._state.hotkey_id)
        if wparam == self._state.hotkey_id and self._command_queue:
            logger.info("Putting SHOW_GUI into command queue.")
            self._command_queue.put(Command.SHOW_GUI)

    def _run_loop(self) -> None:
        """Background thread message loop."""
        self._window = Win32MessageWindow(
            on_clipboard_update=self._process_update,
            on_hotkey=self._on_hotkey,
            hotkey_id=self._state.hotkey_id
        )
        self._window.create_and_pump()

    def start(self) -> None:
        """Start the listener in a background thread."""
        if self._state.thread and self._state.thread.is_alive():
            return

        self._state.thread = threading.Thread(target=self._run_loop, daemon=True)
        self._state.thread.start()

    def stop(self) -> None:
        """Stop the listener."""
        if self._window:
            self._window.destroy()

        if self._state.thread:
            self._state.thread.join(timeout=2.0)
            self._state.thread = None
