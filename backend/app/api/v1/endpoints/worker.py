# file: app/api/v1/endpoints/worker.py

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.models.worker_queue import WorkerQueueStatus
from app.schemas.worker_queue import WorkerQueueRead, WorkerRunOnceResponse
from app.services.worker_queue_service import (
    enqueue_job,
    list_worker_queue,
    worker_queue_to_read,
)
from app.services.worker_service import (
    recover_stale_running_items,
    run_once,
)


router = APIRouter(prefix="/worker", tags=["worker"])


@router.post("/jobs/{job_id}/enqueue", response_model=WorkerQueueRead)
def enqueue_job_endpoint(
    job_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    item = enqueue_job(
        job_id=job_id,
        session=session,
        requested_by_user_id=current_user.id,
    )
    return worker_queue_to_read(item)


@router.post("/run-once", response_model=WorkerRunOnceResponse)
def run_worker_once_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
):
    item = run_once(session=session, worker_id=f"user-{current_user.id}")

    if not item:
        return WorkerRunOnceResponse(
            executed=False,
            message="No queued worker item is ready to run",
            queue_item=None,
        )

    return WorkerRunOnceResponse(
        executed=True,
        message="Worker item executed",
        queue_item=worker_queue_to_read(item),
    )


@router.get("/queue", response_model=list[WorkerQueueRead])
def list_worker_queue_endpoint(
    status_filter: WorkerQueueStatus | None = None,
    job_id: int | None = None,
    schedule_id: int | None = None,
    execution_id: str | None = None,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    items = list_worker_queue(
        session=session,
        status_filter=status_filter,
        job_id=job_id,
        schedule_id=schedule_id,
        execution_id=execution_id,
    )
    return [worker_queue_to_read(item) for item in items]

@router.post("/recover-stale")
def recover_stale_worker_items_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    count = recover_stale_running_items(session)
    return {"detail": f"Recovered stale worker items: {count}"}