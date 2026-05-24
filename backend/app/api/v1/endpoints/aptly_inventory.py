from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.api.deps import get_db_session
from app.clients.aptly_client import AptlyAPIError, AptlyClient
from app.config import get_settings
from app.core.permissions import require_operator, require_viewer
from app.models.aptly_state import AptlyMirrorState, AptlySnapshotState, AptlyPublishState
from app.models.user import User
from app.schemas.aptly_state import (
    AptlyInventorySyncResult,
    AptlyMirrorInventorySummary,
    AptlyMirrorStateDetailRead,
    AptlyMirrorStateRead,
    AptlyMirrorSyncResult,
    AptlySnapshotInventorySummary,
    AptlySnapshotStateDetailRead,
    AptlySnapshotStateRead,
    AptlySnapshotSyncResult,
    AptlyPublishInventorySummary,
    AptlyPublishStateDetailRead,
    AptlyPublishStateRead,
    AptlyPublishSyncResult,
)
from app.services.aptly_inventory_service import (
    get_mirrors_inventory_summary,
    get_publishes_inventory_summary,
    get_snapshots_inventory_summary,
    sync_aptly_inventory,
    sync_aptly_mirrors,
    sync_aptly_publishes,
    sync_aptly_snapshots,
)

router = APIRouter(prefix="/aptly", tags=["aptly"])
settings = get_settings()

def get_aptly_client() -> AptlyClient:
    return AptlyClient(
        base_url=settings.APTLY_API_URL,
        username=settings.APTLY_API_USERNAME,
        password=settings.APTLY_API_PASSWORD,
        token=settings.APTLY_API_TOKEN,
    )

# -----------------------------
# Mirrors
# -----------------------------
@router.post(
    "/sync/mirrors",
    response_model=AptlyMirrorSyncResult,
)
def sync_mirrors_from_aptly(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
    aptly_client: AptlyClient = Depends(get_aptly_client),
):
    """
    Fetch mirror information from the Aptly API and update the local database.

    Required permission:
    operator
    """

    try:
        return sync_aptly_mirrors(
            session=session,
            aptly_client=aptly_client,
        )
    except AptlyAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/mirrors",
    response_model=list[AptlyMirrorStateRead],
)
def list_aptly_mirrors_state(
    distribution: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    List mirrors that have already been synced from Aptly.

    This endpoint does not connect directly to Aptly.
    It reads data from the local database.

    Required permission:
    viewer
    """
    statement = select(AptlyMirrorState)

    if distribution:
        statement = statement.where(
            AptlyMirrorState.distribution == distribution
        )

    if search:
        statement = statement.where(
            AptlyMirrorState.name.contains(search)
        )

    statement = statement.order_by(AptlyMirrorState.name)

    return session.exec(statement).all()


@router.get(
    "/mirrors/summary",
    response_model=AptlyMirrorInventorySummary,
)
def get_aptly_mirrors_summary(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return a summary of mirror inventory status for the dashboard.

    Required permission:
    viewer
    """

    return get_mirrors_inventory_summary(session)


@router.get(
    "/mirrors/{mirror_name}",
    response_model=AptlyMirrorStateDetailRead,
)
def get_aptly_mirror_state(
    mirror_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return details of a specific mirror.

    Required permission:
    viewer
    """

    mirror_state = session.exec(
        select(AptlyMirrorState).where(
            AptlyMirrorState.name == mirror_name
        )
    ).first()

    if not mirror_state:
        raise HTTPException(
            status_code=404,
            detail=f"Mirror '{mirror_name}' not found in local inventory",
        )

    return mirror_state

# -----------------------------
# Snapshots
# -----------------------------
@router.post(
    "/sync/snapshots",
    response_model=AptlySnapshotSyncResult,
)
def sync_snapshots_from_aptly(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
    aptly_client: AptlyClient = Depends(get_aptly_client),
):
    """
    Fetch snapshot information from the Aptly API and update the local database.

    Required permission:
    operator
    """

    try:
        return sync_aptly_snapshots(
            session=session,
            aptly_client=aptly_client,
        )
    except AptlyAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/snapshots",
    response_model=list[AptlySnapshotStateRead],
)
def list_aptly_snapshots_state(
    source_kind: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    source_mirror_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    List snapshots that have already been synced from Aptly.

    This endpoint does not connect directly to Aptly.
    It reads data from the local database.

    Required permission:
    viewer
    """

    statement = select(AptlySnapshotState)

    if source_kind:
        statement = statement.where(
            AptlySnapshotState.source_kind == source_kind
        )

    if origin:
        statement = statement.where(
            AptlySnapshotState.origin == origin
        )

    if source_mirror_name:
        statement = statement.where(
            AptlySnapshotState.source_mirror_name == source_mirror_name
        )

    if search:
        statement = statement.where(
            AptlySnapshotState.name.contains(search)
        )

    statement = statement.order_by(AptlySnapshotState.created_at_aptly.desc())

    return session.exec(statement).all()


@router.get(
    "/snapshots/summary",
    response_model=AptlySnapshotInventorySummary,
)
def get_aptly_snapshots_summary(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return a summary of snapshot inventory status for the dashboard.

    Required permission:
    viewer
    """

    return get_snapshots_inventory_summary(session)


@router.get(
    "/snapshots/{snapshot_name}",
    response_model=AptlySnapshotStateDetailRead,
)
def get_aptly_snapshot_state(
    snapshot_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return details of a specific snapshot.

    Required permission:
    viewer
    """

    snapshot_state = session.exec(
        select(AptlySnapshotState).where(
            AptlySnapshotState.name == snapshot_name
        )
    ).first()

    if not snapshot_state:
        raise HTTPException(
            status_code=404,
            detail=f"Snapshot '{snapshot_name}' not found in local inventory",
        )

    return snapshot_state

# -----------------------------
# Publish
# -----------------------------
@router.post(
    "/sync/publishes",
    response_model=AptlyPublishSyncResult,
)
def sync_publishes_from_aptly(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
    aptly_client: AptlyClient = Depends(get_aptly_client),
):
    """
    Fetch published repository information from the Aptly API and update the local database.

    Required permission:
    operator
    """

    try:
        return sync_aptly_publishes(
            session=session,
            aptly_client=aptly_client,
        )
    except AptlyAPIError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc


@router.get(
    "/publishes",
    response_model=list[AptlyPublishStateRead],
)
def list_aptly_publishes_state(
    prefix: str | None = Query(default=None),
    distribution: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    storage: str | None = Query(default=None),
    origin: str | None = Query(default=None),
    label: str | None = Query(default=None),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    List published repositories that have already been synced from Aptly.

    This endpoint does not connect directly to Aptly.
    It reads data from the local database.

    Required permission:
    viewer
    """

    statement = select(AptlyPublishState)

    if prefix:
        statement = statement.where(
            AptlyPublishState.prefix == prefix
        )

    if distribution:
        statement = statement.where(
            AptlyPublishState.distribution == distribution
        )

    if source_kind:
        statement = statement.where(
            AptlyPublishState.source_kind == source_kind
        )

    if storage:
        statement = statement.where(
            AptlyPublishState.storage == storage
        )

    if origin:
        statement = statement.where(
            AptlyPublishState.origin == origin
        )

    if label:
        statement = statement.where(
            AptlyPublishState.label == label
        )

    if search:
        statement = statement.where(
            AptlyPublishState.path.contains(search)
        )

    statement = statement.order_by(
        AptlyPublishState.prefix,
        AptlyPublishState.distribution,
    )

    return session.exec(statement).all()


@router.get(
    "/publishes/summary",
    response_model=AptlyPublishInventorySummary,
)
def get_aptly_publishes_summary(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return a summary of published repository inventory status for the dashboard.

    Required permission:
    viewer
    """

    return get_publishes_inventory_summary(session)


@router.get(
    "/publishes/{publish_id}",
    response_model=AptlyPublishStateDetailRead,
)
def get_aptly_publish_state(
    publish_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    """
    Return details of a specific published repository entry.

    Required permission:
    viewer
    """

    publish_state = session.get(AptlyPublishState, publish_id)

    if not publish_state:
        raise HTTPException(
            status_code=404,
            detail=f"Published repository entry with id '{publish_id}' not found",
        )

    return publish_state

# -----------------------------
# SYNC ALL
# -----------------------------
@router.post(
    "/sync",
    response_model=AptlyInventorySyncResult,
)
def sync_all_aptly_inventory(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_operator),
    aptly_client: AptlyClient = Depends(get_aptly_client),
):
    """
    Sync all Aptly inventory resources into the local database.

    Resources:
    - mirrors
    - snapshots
    - publishes

    Required permission:
    operator
    """

    return sync_aptly_inventory(
        session=session,
        aptly_client=aptly_client,
    )