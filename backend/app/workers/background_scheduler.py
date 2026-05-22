# file: app/services/background_scheduler.py

import logging
import threading
import time

from sqlmodel import Session

from app.config import get_settings
from app.db.session import engine
from app.services.scheduler_service import process_due_schedules

settings = get_settings()
logger = logging.getLogger("aptly-background-scheduler")

_stop_event = threading.Event()
_scheduler_thread: threading.Thread | None = None


def scheduler_loop() -> None:
    logger.info("Background scheduler started")

    while not _stop_event.is_set():
        try:
            with Session(engine) as session:
                processed = process_due_schedules(session)

                if processed:
                    logger.info("Processed due schedules: %s", processed)

            time.sleep(settings.SCHEDULER_POLL_INTERVAL_SECONDS)

        except Exception:
            logger.exception("Background scheduler loop failed")
            time.sleep(settings.SCHEDULER_POLL_INTERVAL_SECONDS)

    logger.info("Background scheduler stopped")


def start_background_scheduler() -> None:
    global _scheduler_thread

    if _scheduler_thread and _scheduler_thread.is_alive():
        return

    _stop_event.clear()

    _scheduler_thread = threading.Thread(
        target=scheduler_loop,
        name="aptly-background-scheduler",
        daemon=True,
    )
    _scheduler_thread.start()


def stop_background_scheduler() -> None:
    _stop_event.set()

    if _scheduler_thread and _scheduler_thread.is_alive():
        _scheduler_thread.join(timeout=10)