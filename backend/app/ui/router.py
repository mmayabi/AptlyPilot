from fastapi import APIRouter

from app.ui import auth, dashboard

ui_router = APIRouter()

ui_router.include_router(auth.router)
ui_router.include_router(dashboard.router)