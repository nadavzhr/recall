"""Main CustomTkinter application window."""

import queue
import customtkinter as ctk
import time

from recall.storage.db import RecallDatabase
from recall.clipboard.operations import set_clipboard_text, simulate_paste
from recall.models import ClipboardEntry
from recall.ui.commands import Command
from recall.ui.components.item_widget import ItemWidget
from recall import config

class RecallUI(ctk.CTk):
    """Main window for Recall UI."""

    def __init__(self, db: RecallDatabase, command_queue: queue.Queue[Command]) -> None:
        """Initialize the UI.

        Args:
            db: Database instance for querying clipboard history.
            command_queue: Queue to listen for commands.
        """
        super().__init__()
        self.db = db
        self.command_queue = command_queue

        # Configure window
        self.title("Recall")
        self.geometry(f"{config.UI_WIDTH}x{config.UI_HEIGHT}")
        
        # Make the window hidden by default until hotkey is pressed
        self.withdraw()
        
        # Basic styling
        ctk.set_appearance_mode("dark")
        
        # Configure the main window background to be slightly lighter than pure black
        self.configure(fg_color="#18181b")

        # Keep window on top when visible
        self.attributes("-topmost", True)
        
        # Modern Frameless 'Spotlight' look
        self.overrideredirect(True)

        # Prevent the application from closing when X is clicked (if borders were shown)
        self.protocol("WM_DELETE_WINDOW", self._hide_window)

        self._build_ui()
        self._poll_commands()
        
        # Close on Escape
        self.bind("<Escape>", lambda e: self._hide_window())

    def _build_ui(self) -> None:
        """Construct the UI widgets."""
        # Main padding wrapper to give breathing room from the edges
        self.main_frame = ctk.CTkFrame(self, fg_color="#18181b", corner_radius=12, border_width=1, border_color="#27272a")
        self.main_frame.pack(fill="both", expand=True, padx=0, pady=0)
        
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        # Header frame for search and close button
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="ew")
        self.header_frame.grid_columnconfigure(0, weight=1)

        # Search bar
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self._on_search_change)
        self.search_entry = ctk.CTkEntry(
            self.header_frame,
            textvariable=self.search_var,
            placeholder_text="Search clipboard...",
            height=60,
            corner_radius=8,
            border_width=0,
            fg_color="#27272a",
            text_color="#e4e4e7",
            placeholder_text_color="#a1a1aa",
            font=("Segoe UI", 20)
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))

        # Close button
        self.close_btn = ctk.CTkButton(
            self.header_frame,
            text="✕",
            width=60,
            height=60,
            corner_radius=8,
            fg_color="#27272a",
            hover_color="#ef4444", # Red hover
            text_color="#a1a1aa",
            font=("Segoe UI", 20, "bold"),
            command=self._hide_window
        )
        self.close_btn.grid(row=0, column=1, sticky="e")

        # Scrollable list
        self.scrollable_frame = ctk.CTkScrollableFrame(
            self.main_frame, 
            fg_color="transparent",
            scrollbar_button_color="#3f3f46",
            scrollbar_button_hover_color="#52525b"
        )
        self.scrollable_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.scrollable_frame.grid_columnconfigure(0, weight=1)

    def _on_search_change(self, *args) -> None:
        """Filter items based on search query."""
        self._refresh_items(search_query=self.search_var.get())

    def _refresh_items(self, search_query: str = "") -> None:
        """Load items from database and render them."""
        # Clear existing
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        # Fetch from DB.
        items = self.db.get_recent(limit=50)
        
        if search_query:
            query_lower = search_query.lower()
            items = [item for item in items if item.content_text and query_lower in item.content_text.lower()]

        for i, item in enumerate(items):
            # We don't skip empty content texts here anymore to support generic display 
            # if images/other contents exist, though currently only text is handled.
            widget = ItemWidget(self.scrollable_frame, item=item, on_click=self._on_item_click)
            widget.grid(row=i, column=0, pady=4, padx=10, sticky="ew")

    def _on_item_click(self, item: ClipboardEntry) -> None:
        """Handle clicking an item: move to top, copy, and paste."""
        if item.content_type == "text" and item.content_text:
            # 1. Update database to move it to the top
            self.db.insert_entry("text", item.content_text)
            
            # 2. Set to Windows clipboard
            set_clipboard_text(item.content_text)
            
            # 3. Hide window
            self._hide_window()

            # 4. Simulate Paste (small delay to allow window to lose focus)
            self.after(50, simulate_paste)

    def _show_window(self) -> None:
        """Display the UI."""
        self._refresh_items()
        self.search_var.set("")
        
        # Center window on screen
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        window_width = 600
        window_height = 500
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2) - 100 # slightly higher than center
        self.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        self.deiconify()
        self.lift()
        self.focus_force()
        self.search_entry.focus()

    def _hide_window(self, event=None) -> None:
        """Hide the UI."""
        self.withdraw()

    def _poll_commands(self) -> None:
        """Check for messages from background threads."""
        try:
            while True:
                cmd = self.command_queue.get_nowait()
                if cmd == Command.SHOW_GUI:
                    import logging
                    logging.getLogger(__name__).info("SHOW_GUI command received by UI thread. Showing window.")
                    self._show_window()
        except queue.Empty:
            pass
        
        # Poll again in 100ms
        self.after(100, self._poll_commands)
