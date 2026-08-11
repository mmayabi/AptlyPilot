from fastapi import APIRouter

from app.ui import auth, dashboard, repositories

ui_router = APIRouter()

ui_router.include_router(auth.router)
ui_router.include_router(dashboard.router)
ui_router.include_router(repositories.router)