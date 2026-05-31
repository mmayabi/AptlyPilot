from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, aptly_inventory, aptly_dashboard, repos, jobs, templates, scripts, worker, schedules
api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(aptly_inventory.router)
api_router.include_router(repos.router)
api_router.include_router(aptly_dashboard.router)
api_router.include_router(templates.router)
api_router.include_router(jobs.router)
api_router.include_router(scripts.router)
api_router.include_router(worker.router)
api_router.include_router(schedules.router)