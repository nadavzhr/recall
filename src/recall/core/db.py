"""Database access for clipboard history."""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3

from recall.models import ClipboardEntry

logger = logging.getLogger(__name__)


class RecallDatabase:
    """Manages storage for clipboard entries with de-duplication and limits."""

    def __init__(
        self,
        db_name: str = ".recall.db",
        max_items: int = 200,
    ) -> None:
        """Initialize the database and ensure the schema exists."""
        if max_items <= 0:
            raise ValueError("max_items must be positive.")

        self.db_path = Path.home() / db_name
        self.max_items = max_items
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Create a new SQLite connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        """Create the clipboard history table and migration logic."""
        with self._connect() as conn:
            cursor = conn.cursor()
            # We use a unique constraint on content to allow for 'Move-to-Top' logic.
            # Note: For large text, we might want to index a hash instead, 
            # but for 200 items, SQLite handles text comparison very efficiently.
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS clipboard_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type TEXT NOT NULL,
                    content_text TEXT,
                    content_data BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(content_text, content_data)
                )
                """
            )
            
            # Migration: Ensure content_data exists
            cursor.execute("PRAGMA table_info(clipboard_history)")
            columns = [info[1] for info in cursor.fetchall()]
            if "content_data" not in columns:
                cursor.execute("ALTER TABLE clipboard_history ADD COLUMN content_data BLOB")
            
            conn.commit()

    def insert_entry(
        self,
        content_type: str,
        content_text: str | None = None,
        content_data: bytes | None = None,
    ) -> None:
        """Insert a clipboard entry or move an existing entry to the top of the history."""
        if not content_type:
            raise ValueError("content_type must be non-empty.")

        if content_type == "text" and content_text is not None and not content_text.strip():
            return

        with self._connect() as conn:
            cursor = conn.cursor()

            # IMPLEMENTATION NOTE: Move-to-Top De-duplication Strategy
            # 1. We check if the exact content (text or binary) already exists.
            # 2. If it does, we update its timestamp instead of creating a duplicate.
            # 3. We use the 'IS' operator because it is null-safe (NULL IS NULL is true),
            #    allowing us to match entries with optional fields.
            # 4. We avoid 'UPSERT' because UNIQUE constraints on nullable columns 
            #    don't trigger conflicts for NULL values in SQLite.
            cursor.execute(
                "SELECT id FROM clipboard_history WHERE content_text IS ? AND content_data IS ?",
                (content_text, content_data),
            )
            existing = cursor.fetchone()

            if existing:
                # Update timestamp to move to top
                cursor.execute(
                    "UPDATE clipboard_history SET timestamp = CURRENT_TIMESTAMP WHERE id = ?",
                    (existing[0],),
                )
            else:
                # Insert new
                cursor.execute(
                    """
                    INSERT INTO clipboard_history (content_type, content_text, content_data)
                    VALUES (?, ?, ?)
                    """,
                    (content_type, content_text, content_data),
                )
            conn.commit()

        self._enforce_limit()

    def _enforce_limit(self) -> None:
        """Keep the database size bounded efficiently."""
        with self._connect() as conn:
            cursor = conn.cursor()
            # We delete by timestamp to support the 'Move-to-Top' logic
            cursor.execute(
                """
                DELETE FROM clipboard_history
                WHERE id NOT IN (
                    SELECT id FROM clipboard_history
                    ORDER BY timestamp DESC
                    LIMIT ?
                )
                """,
                (self.max_items,),
            )
            conn.commit()

    def get_recent(self, limit: int = 10) -> list[ClipboardEntry]:
        """Fetch recent entries ordered by timestamp (newest first)."""
        if limit <= 0:
            return []

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content_type, content_text, content_data, timestamp
                FROM clipboard_history
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        return [ClipboardEntry(*row) for row in rows]
