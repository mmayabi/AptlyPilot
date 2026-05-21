from fastapi import APIRouter

from app.api.v1.endpoints import auth, health, repos, jobs, job_templates

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(repos.router)
api_router.include_router(jobs.router)
api_router.include_router(job_templates.router)