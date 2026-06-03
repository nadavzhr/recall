"""Console entrypoint for the Recall clipboard manager."""

import logging
import queue
import time

from recall.core.db import RecallDatabase
from recall.core.listener import ClipboardListener, ClipboardEvent
from recall.utils import truncate_text

logger = logging.getLogger(__name__)


def process_event(event: ClipboardEvent, database: RecallDatabase) -> None:
    """Handle a clipboard event by persisting it and logging it."""
    try:
        database.insert_entry(
            content_type=event.content_type,
            content_text=event.content_text,
            content_data=event.content_data,
        )
        if event.content_type == "text" and event.content_text:
            logger.info("Ingested text: %s", truncate_text(event.content_text))
        else:
            size = len(event.content_data) if event.content_data else 0
            logger.info("Ingested %s (%d bytes)", event.content_type, size)
    except Exception:
        logger.exception("Failed to store clipboard item")


def main() -> None:
    """Run the clipboard listener as a background-ready process."""
    # Configure logging for production: Level first, then UTC time, then message.
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] [%(asctime)s] %(message)s",
    )
    logging.Formatter.converter = time.gmtime  # Use UTC (GMT) for timestamps

    logger.info("Recall service starting.")

    database = RecallDatabase()
    event_queue: queue.Queue[ClipboardEvent] = queue.Queue()
    clipboard_listener = ClipboardListener(event_queue=event_queue)

    try:
        clipboard_listener.start()
        logger.info("Recall service active and listening.")

        while True:
            try:
                # Polling the queue with a timeout allows checking for signals
                event = event_queue.get(timeout=0.1)
                process_event(event, database)
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        logger.info("Recall service received interrupt signal.")
    except Exception:
        logger.exception("Recall service encountered a fatal error.")
    finally:
        clipboard_listener.stop()
        logger.info("Recall service shutdown complete.")


if __name__ == "__main__":
    main()
