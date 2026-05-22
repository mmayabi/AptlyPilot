# for run worker as seprate container:
# main.py:
#from collections.abc import AsyncGenerator
#from contextlib import asynccontextmanager
#
#from fastapi import FastAPI
#
#from app.api.v1.router import api_router
#from app.config import get_settings
#from app.db.init_db import init_db
#from app.logging import setup_logging
#
#
#@asynccontextmanager
#async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
#    init_db()
#    yield
#
#
#def create_app() -> FastAPI:
#    setup_logging()
#    settings = get_settings()
#
#    app = FastAPI(
#        title=settings.PROJECT_NAME,
#        debug=settings.DEBUG,
#        version="0.1.0",
#        lifespan=lifespan,
#    )
#
#    app.include_router(
#        api_router,
#        prefix=settings.API_V1_PREFIX,
#    )
#
#    return app
#
#
#app = create_app()
## docker-compose.py
#services:
#  api:
#    build: .
#    container_name: aptlypilot-api
#    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
#    depends_on:
#      - postgres
#    env_file:
#      - .env
#    volumes:
#      - .:/app
#
#  worker:
#    build: .
#    container_name: aptlypilot-worker
#    command: python -m app.worker_main
#    depends_on:
#      - postgres
#    env_file:
#      - .env
#    volumes:
#      - .:/app
#    restart: unless-stopped


# file: app/worker_main.py

import logging
import time

from sqlmodel import Session

from app.config import get_settings
from app.db.session import engine
from app.services.worker_service import (
    recover_stale_running_items,
    run_once,
)

settings = get_settings()

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

logger = logging.getLogger("aptly-worker")


def run_worker_loop() -> None:
    worker_id = "aptly-worker-1"

    logger.info("Worker started: %s", worker_id)

    while True:
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

        except KeyboardInterrupt:
            logger.info("Worker stopped by keyboard interrupt")
            break

        except Exception:
            logger.exception("Worker loop failed")
            time.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_worker_loop()