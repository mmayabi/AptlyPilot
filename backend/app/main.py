from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.config import get_settings
from app.db.init_db import init_db
from app.logging import setup_logging
from app.workers.background_worker import (
    start_background_worker,
    stop_background_worker,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()

    init_db()

    if settings.ENABLE_IN_APP_WORKER:
        start_background_worker()

    try:
        yield
    finally:
        if settings.ENABLE_IN_APP_WORKER:
            stop_background_worker()


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        debug=settings.DEBUG,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(
        api_router,
        prefix=settings.API_V1_PREFIX,
    )

    return app


app = create_app()