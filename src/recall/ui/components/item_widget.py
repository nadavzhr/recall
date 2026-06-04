"""Reusable UI component for a single clipboard entry."""

from typing import Callable
import customtkinter as ctk
import io
from PIL import Image

from recall.models import ClipboardEntry

class ItemWidget(ctk.CTkButton):
    """A widget representing a single clipboard history item."""
    
    def __init__(
        self, 
        master: ctk.CTkFrame | ctk.CTkScrollableFrame, 
        item: ClipboardEntry, 
        on_click: Callable[[ClipboardEntry], None], 
        **kwargs
    ):
        """Initialize the item widget.
        
        Args:
            master: The parent widget.
            item: The clipboard entry to display.
            on_click: Callback when the item is clicked (double-clicked).
        """
        self.item = item
        self.on_click_callback = on_click
        
        preview_text = ""
        image = None
        
        if item.content_type == "text" and item.content_text:
            preview_text = item.content_text.strip().replace("\n", " ↵ ")
            if len(preview_text) > 100:
                preview_text = preview_text[:97] + "..."
        elif item.content_type == "image" and item.thumbnail_data:
            try:
                pil_image = Image.open(io.BytesIO(item.thumbnail_data))
                image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=pil_image.size)
            except Exception:
                preview_text = "<Corrupted Image>"
        else:
            preview_text = f"<{item.content_type}>"

        super().__init__(
            master,
            text=preview_text,
            image=image,
            anchor="w" if not image else "center",
            height=50 if image is None else image.cget("size")[1] + 20,
            corner_radius=6,
            fg_color="transparent",
            text_color="#e4e4e7",
            hover_color="#27272a",
            font=("Segoe UI", 14),
            **kwargs
        )
        
        # Bind double left click to copy/paste action
        self.bind("<Double-Button-1>", self._handle_click)
        # Bind Return key if keyboard navigation is added later
        self.bind("<Return>", self._handle_click)

    def _handle_click(self, event=None) -> None:
        """Trigger the click callback."""
        self.on_click_callback(self.item)

