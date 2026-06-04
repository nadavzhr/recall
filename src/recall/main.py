"""Console entrypoint for the Recall clipboard manager."""

import logging
import queue
import time
import threading

from recall import config
from recall.storage.db import RecallDatabase
from recall.clipboard.listener import ClipboardListener
from recall.utils import truncate_text
from recall.ui.views.main_window import RecallUI
from recall.models import ClipboardEvent
from recall.ui.commands import Command

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


def ingest_worker(event_queue: queue.Queue[ClipboardEvent], database: RecallDatabase) -> None:
    """Background thread to process events from the listener queue."""
    while True:
        try:
            event = event_queue.get(timeout=1.0)
            process_event(event, database)
        except queue.Empty:
            continue
        except Exception:
            logger.exception("Error in ingest worker")


def main() -> None:
    """Run the clipboard manager and UI."""
    # Configure logging for production: Level first, then UTC time, then message.
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] [%(asctime)s] %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE),
            logging.StreamHandler()
        ]
    )
    logging.Formatter.converter = time.gmtime  # Use UTC (GMT) for timestamps

    logger.info("Recall service starting.")

    database = RecallDatabase()
    event_queue: queue.Queue[ClipboardEvent] = queue.Queue()
    command_queue: queue.Queue[Command] = queue.Queue()
    
    clipboard_listener = ClipboardListener(event_queue=event_queue, command_queue=command_queue)

    # Start the DB ingestion thread
    ingest_thread = threading.Thread(target=ingest_worker, args=(event_queue, database), daemon=True)
    ingest_thread.start()

    try:
        import keyboard
        clipboard_listener.start()
        
        # Setup global hotkey using keyboard module
        def trigger_gui():
            logger.info("Hotkey pressed. Enqueueing SHOW_GUI command.")
            command_queue.put(Command.SHOW_GUI)
            
        keyboard.add_hotkey(config.HOTKEY_STRING, trigger_gui)
        
        logger.info("Recall service active and listening. Press %s to show UI.", config.HOTKEY_STRING)

        # Run the UI on the main thread
        app = RecallUI(db=database, command_queue=command_queue)
        app.mainloop()  # type: ignore

    except KeyboardInterrupt:
        logger.info("Recall service received interrupt signal.")
    except Exception:
        logger.exception("Recall service encountered a fatal error.")
    finally:
        clipboard_listener.stop()
        logger.info("Recall service shutdown complete.")


if __name__ == "__main__":
    main()
