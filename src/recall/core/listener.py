"""Windows clipboard listener for multi-format updates."""

import ctypes
import threading
import logging
from queue import Queue

import pywintypes
import win32api
import win32clipboard
import win32con
import win32gui

from recall.models import ClipboardEvent

logger = logging.getLogger(__name__)

ERROR_CLASS_ALREADY_EXISTS = 1410
WM_CLIPBOARDUPDATE = 0x031D
WINDOW_CLASS_NAME = "ProjectRecallListener"
WINDOW_TITLE = "RecallHiddenWindow"


class ClipboardListener:
    """Listen for clipboard updates in a background thread and queue events."""

    def __init__(self, event_queue: Queue[ClipboardEvent], command_queue: Queue[str] | None = None) -> None:
        """Create a clipboard listener.

        Args:
            event_queue: Thread-safe queue where updates are posted.
            command_queue: Optional queue to send application commands (e.g., hotkey triggers).
        """
        self._queue = event_queue
        self._command_queue = command_queue
        self._last_content_hash: int | None = None
        self._hwnd: int | None = None
        self._thread: threading.Thread | None = None
        self._hotkey_id = 1

    def _process_update(self) -> None:
        """Inspect the clipboard and queue events for supported formats."""
        clipboard_open = False
        try:
            win32clipboard.OpenClipboard()  # type: ignore
            clipboard_open = True

            # 1. Handle Text
            if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
                text = win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)  # type: ignore
                content_hash = hash(text)
                if content_hash != self._last_content_hash:
                    self._last_content_hash = content_hash
                    self._queue.put(ClipboardEvent(content_type="text", content_text=text))

            # 2. Handle Images (Placeholder for future implementation)
            elif win32clipboard.IsClipboardFormatAvailable(win32con.CF_DIB):
                pass

        except pywintypes.error as e:
            logger.debug("Clipboard access error: %s", e)
        finally:
            if clipboard_open:
                try:
                    win32clipboard.CloseClipboard()  # type: ignore
                except pywintypes.error:
                    pass

    def _wndproc(self, hwnd: int, msg: int, wparam: int, lparam: int) -> int:
        """Handle Win32 messages."""
        if msg == WM_CLIPBOARDUPDATE:
            self._process_update()
            return 0

        if msg == win32con.WM_HOTKEY:
            logger.info("WM_HOTKEY received! wparam: %s, hotkey_id: %s", wparam, self._hotkey_id)
            if wparam == self._hotkey_id and self._command_queue:
                logger.info("Putting SHOW_GUI into command queue.")
                self._command_queue.put("SHOW_GUI")
            return 0

        if msg == win32con.WM_CLOSE:
            win32gui.DestroyWindow(hwnd)
            return 0

        if msg == win32con.WM_DESTROY:
            ctypes.windll.user32.UnregisterHotKey(hwnd, self._hotkey_id)
            ctypes.windll.user32.RemoveClipboardFormatListener(hwnd)
            self._hwnd = None
            win32gui.PostQuitMessage(0)
            return 0

        return win32gui.DefWindowProc(hwnd, msg, wparam, lparam)

    def _run_loop(self) -> None:
        """Background thread message loop."""
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

        self._hwnd = win32gui.CreateWindowEx(  # type: ignore
            0, WINDOW_CLASS_NAME, WINDOW_TITLE,
            0, 0, 0, 0, 0,
            win32con.HWND_MESSAGE,
            0, wc.hInstance, None
        )

        if not self._hwnd:  # type: ignore
            logger.error("Failed to create message window")
            return

        if not ctypes.windll.user32.AddClipboardFormatListener(self._hwnd):  # type: ignore
            win32gui.DestroyWindow(self._hwnd)  # type: ignore
            self._hwnd = None
            logger.error("Failed to add clipboard format listener")
            return

        win32gui.PumpMessages()

    def start(self) -> None:
        """Start the listener in a background thread."""
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the listener."""
        if self._hwnd:
            win32gui.PostMessage(self._hwnd, win32con.WM_CLOSE, 0, 0)

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
