"""Centralized configuration for the Recall application."""

from pathlib import Path

# --- Application Directory ---
APP_DIR = Path.home() / ".recall"
APP_DIR.mkdir(parents=True, exist_ok=True)

# --- Database ---
DB_NAME = "recall.db"
DB_PATH = APP_DIR / DB_NAME
MAX_ITEMS = 200

# --- Logging ---
LOG_FILE = APP_DIR / "recall.log"

# --- Hotkey ---
HOTKEY_STRING = "ctrl+alt+v"

# --- UI Settings ---
UI_WIDTH = 600
UI_HEIGHT = 500
