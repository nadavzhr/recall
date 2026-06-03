"""Centralized configuration for the Recall application."""

from pathlib import Path

# --- Database ---
DB_NAME = ".recall.db"
DB_PATH = Path.home() / DB_NAME
MAX_ITEMS = 200

# --- Logging ---
LOG_FILE = Path.home() / ".recall.log"

# --- Hotkey ---
HOTKEY_STRING = "ctrl+alt+v"

# --- UI Settings ---
UI_WIDTH = 600
UI_HEIGHT = 500
