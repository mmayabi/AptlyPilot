from fastapi import APIRouter

from app.ui import auth, dashboard, repositories, schedules, tasks

ui_router = APIRouter()

ui_router.include_router(auth.router)
ui_router.include_router(dashboard.router)
ui_router.include_router(repositories.router)
ui_router.include_router(schedules.router)
ui_router.include_router(tasks.router)
