"""Reusable UI component for a single clipboard entry."""

from typing import Callable
import tkinter as tk
import customtkinter as ctk
import io
from PIL import Image

from recall.models import ClipboardEntry


class Tooltip:
    """Simple hover tooltip for a widget."""

    def __init__(self, widget: ctk.CTkBaseClass, text: str):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show, add="+")
        self.widget.bind("<Leave>", self.hide, add="+")

    def show(self, event=None):
        if self.tooltip_window is not None:
            return

        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5

        # Use standard tk.Toplevel to avoid CustomTkinter async initialization issues during rapid hover
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        # Ensure it floats above
        self.tooltip_window.attributes("-topmost", True)
        self.tooltip_window.configure(bg="#3f3f46")

        label = ctk.CTkLabel(
            self.tooltip_window,
            text=self.text,
            fg_color="#3f3f46",
            text_color="#e4e4e7",
            corner_radius=4,
            font=("Segoe UI", 12),
        )
        label.pack(padx=6, pady=4)

    def hide(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None


class ItemWidget(ctk.CTkButton):
    """A widget representing a single clipboard history item."""

    def __init__(
        self,
        master: ctk.CTkFrame | ctk.CTkScrollableFrame,
        item: ClipboardEntry,
        on_click: Callable[[ClipboardEntry], None],
        on_pin: Callable[[ClipboardEntry], None],
        on_delete: Callable[[ClipboardEntry], None],
        **kwargs,
    ):
        """Initialize the item widget.

        Args:
            master: The parent widget.
            item: The clipboard entry to display.
            on_click: Callback when the item is clicked (double-clicked).
            on_pin: Callback when the item is pinned/unpinned.
            on_delete: Callback when the item is deleted.
        """
        self.item = item
        self.on_click_callback = on_click
        self.on_pin_callback = on_pin
        self.on_delete_callback = on_delete

        preview_text = ""
        image = None

        if item.content_type == "text" and item.content_text:
            preview_text = item.content_text.strip().replace("\n", " ↵ ")
            if len(preview_text) > 100:
                preview_text = preview_text[:97] + "..."
        elif item.content_type == "image" and item.thumbnail_data:
            try:
                pil_image = Image.open(io.BytesIO(item.thumbnail_data))
                image = ctk.CTkImage(
                    light_image=pil_image, dark_image=pil_image, size=pil_image.size
                )
            except Exception:
                preview_text = "<Corrupted Image>"
        else:
            preview_text = f"<{item.content_type}>"

        if item.is_pinned:
            preview_text = f"📌 {preview_text}"

        super().__init__(
            master,
            text=preview_text,
            image=image,
            anchor="w" if not image else "center",
            height=50 if image is None else image.cget("size")[1] + 20,
            corner_radius=6,
            fg_color="#27272a" if item.is_pinned else "transparent",
            text_color="#e4e4e7",
            hover_color="#3f3f46",
            font=("Segoe UI", 14, "bold" if item.is_pinned else "normal"),
            **kwargs,
        )

        # Tooltip formatting
        kb_size = item.size_bytes / 1024
        added_str = item.timestamp.strftime("%Y-%m-%d %H:%M")
        used_str = item.last_used_timestamp.strftime("%Y-%m-%d %H:%M")
        tooltip_text = (
            f"Size: {kb_size:.1f} KB\nAdded: {added_str}\nLast Used: {used_str}"
        )
        self.tooltip = Tooltip(self, tooltip_text)

        # Bindings
        self.bind("<Double-Button-1>", self._handle_click)
        self.bind("<Return>", self._handle_click)

        # Context menu binding (Right Click)
        self.bind("<Button-3>", self._show_context_menu)

        # Allow selection-based deletion (Delete key) if we have focus
        self.bind("<Delete>", lambda e: self._handle_delete())

    def _handle_click(self, event=None) -> None:
        """Trigger the click callback."""
        self.on_click_callback(self.item)

    def _handle_pin(self) -> None:
        """Trigger the pin callback."""
        self.on_pin_callback(self.item)

    def _handle_delete(self) -> None:
        """Trigger the delete callback."""
        self.on_delete_callback(self.item)

    def _show_context_menu(self, event) -> None:
        """Show the right-click context menu."""
        menu = tk.Menu(
            self, tearoff=0, bg="#27272a", fg="#e4e4e7", font=("Segoe UI", 10)
        )
        pin_label = "Unpin" if self.item.is_pinned else "Pin"
        menu.add_command(label=pin_label, command=self._handle_pin)
        menu.add_separator()
        menu.add_command(label="Delete", command=self._handle_delete)

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
