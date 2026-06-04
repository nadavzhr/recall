"""Database access for clipboard history."""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
from datetime import datetime

from recall.models import ClipboardEntry
from recall import config

logger = logging.getLogger(__name__)


class RecallDatabase:
    """Manages storage for clipboard entries with de-duplication and limits."""

    def __init__(self) -> None:
        """Initialize the database and ensure the schema exists."""
        self.db_path: Path = config.DB_PATH
        self.max_items: int = config.MAX_ITEMS
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
                    thumbnail_data BLOB,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    is_pinned BOOLEAN DEFAULT 0,
                    last_used_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    size_bytes INTEGER DEFAULT 0,
                    UNIQUE(content_text, content_data)
                )
                """
            )

            # Migration: Ensure new columns exist
            cursor.execute("PRAGMA table_info(clipboard_history)")
            columns = [info[1] for info in cursor.fetchall()]
            if "content_data" not in columns:
                cursor.execute(
                    "ALTER TABLE clipboard_history ADD COLUMN content_data BLOB"
                )
            if "thumbnail_data" not in columns:
                cursor.execute(
                    "ALTER TABLE clipboard_history ADD COLUMN thumbnail_data BLOB"
                )
            if "is_pinned" not in columns:
                cursor.execute(
                    "ALTER TABLE clipboard_history ADD COLUMN is_pinned BOOLEAN DEFAULT 0"
                )
            if "last_used_timestamp" not in columns:
                # SQLite ALTER TABLE does not support CURRENT_TIMESTAMP as a default.
                cursor.execute(
                    "ALTER TABLE clipboard_history ADD COLUMN last_used_timestamp DATETIME"
                )
                # Backfill last_used_timestamp with timestamp
                cursor.execute(
                    "UPDATE clipboard_history SET last_used_timestamp = timestamp"
                )
            if "size_bytes" not in columns:
                cursor.execute(
                    "ALTER TABLE clipboard_history ADD COLUMN size_bytes INTEGER DEFAULT 0"
                )

            conn.commit()

    def insert_entry(
        self,
        content_type: str,
        content_text: str | None = None,
        content_data: bytes | None = None,
        thumbnail_data: bytes | None = None,
    ) -> None:
        """Insert a clipboard entry or move an existing entry to the top of the history."""
        if not content_type:
            raise ValueError("content_type must be non-empty.")

        if (
            content_type == "text"
            and content_text is not None
            and not content_text.strip()
        ):
            return

        # Calculate size
        size_bytes = 0
        if content_text is not None:
            size_bytes = len(content_text.encode("utf-8"))
        elif content_data is not None:
            size_bytes = len(content_data)

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
                # Update last_used_timestamp to move to top, keeping original timestamp (creation date)
                cursor.execute(
                    "UPDATE clipboard_history SET last_used_timestamp = CURRENT_TIMESTAMP WHERE id = ?",
                    (existing[0],),
                )
            else:
                # Insert new (explicitly pass CURRENT_TIMESTAMP to last_used_timestamp in case of altered table)
                cursor.execute(
                    """
                    INSERT INTO clipboard_history (content_type, content_text, content_data, thumbnail_data, size_bytes, last_used_timestamp)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        content_type,
                        content_text,
                        content_data,
                        thumbnail_data,
                        size_bytes,
                    ),
                )
            conn.commit()

        self._enforce_limit()

    def _enforce_limit(self) -> None:
        """Keep the database size bounded efficiently, protecting pinned items."""
        with self._connect() as conn:
            cursor = conn.cursor()
            # We delete unpinned items beyond the limit, sorted by last usage
            cursor.execute(
                """
                DELETE FROM clipboard_history
                WHERE is_pinned = 0 AND id NOT IN (
                    SELECT id FROM clipboard_history
                    WHERE is_pinned = 0
                    ORDER BY last_used_timestamp DESC
                    LIMIT ?
                )
                """,
                (self.max_items,),
            )
            conn.commit()

    def get_recent(self, limit: int = 10) -> list[ClipboardEntry]:
        """Fetch recent entries ordered by pin status then last usage."""
        if limit <= 0:
            return []

        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, content_type, content_text, content_data, thumbnail_data, timestamp, is_pinned, last_used_timestamp, size_bytes
                FROM clipboard_history
                ORDER BY is_pinned DESC, last_used_timestamp DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()

        entries = []
        for row in rows:
            # SQLite CURRENT_TIMESTAMP is 'YYYY-MM-DD HH:MM:SS'
            dt = datetime.strptime(row[5], "%Y-%m-%d %H:%M:%S")
            last_used_dt = datetime.strptime(row[7], "%Y-%m-%d %H:%M:%S")
            entries.append(
                ClipboardEntry(
                    item_id=row[0],
                    content_type=row[1],
                    content_text=row[2],
                    content_data=row[3],
                    thumbnail_data=row[4],
                    timestamp=dt,
                    is_pinned=bool(row[6]),
                    last_used_timestamp=last_used_dt,
                    size_bytes=row[8],
                )
            )
        return entries

    def toggle_pin(self, item_id: int) -> None:
        """Toggle the pinned status of a clipboard entry."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE clipboard_history SET is_pinned = NOT is_pinned WHERE id = ?",
                (item_id,),
            )
            conn.commit()

    def delete_entry(self, item_id: int) -> None:
        """Delete a specific clipboard entry by its ID."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clipboard_history WHERE id = ?", (item_id,))
            conn.commit()
