# file: app/services/background_worker.py

import logging
import threading
import time

from sqlmodel import Session

from app.config import get_settings
from app.db.session import engine
from app.services.worker_service import recover_stale_running_items, run_once

settings = get_settings()
logger = logging.getLogger("aptly-background-worker")

_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def worker_loop() -> None:
    worker_id = "in-app-worker-1"
    logger.info("Background worker started: %s", worker_id)

    while not _stop_event.is_set():
        try:
            with Session(engine) as session:
                recovered = recover_stale_running_items(session)
                if recovered:
                    logger.warning("Recovered stale worker items: %s", recovered)

                item = run_once(session=session, worker_id=worker_id)

                if item:
                    logger.info(
                        "Executed queue item id=%s job_id=%s job_step_id=%s status=%s",
                        item.id,
                        item.job_id,
                        item.job_step_id,
                        item.status,
                    )
                else:
                    time.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

        except Exception:
            logger.exception("Background worker loop failed")
            time.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

    logger.info("Background worker stopped")


def start_background_worker() -> None:
    global _worker_thread

    if _worker_thread and _worker_thread.is_alive():
        return

    _stop_event.clear()

    _worker_thread = threading.Thread(
        target=worker_loop,
        name="aptly-background-worker",
        daemon=True,
    )
    _worker_thread.start()


def stop_background_worker() -> None:
    _stop_event.set()

    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=10)