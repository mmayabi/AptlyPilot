from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_viewer
from app.models.user import User
from app.services.aptly_dashboard_service import (
    get_dashboard_compliance,
    get_dashboard_provider_release_detail,
    get_dashboard_provider_releases,
    get_dashboard_providers,
    get_dashboard_repositories,
    get_dashboard_repository_by_id,
    get_dashboard_repository_by_name,
    get_dashboard_summary,
)

router = APIRouter(prefix="/aptly/dashboard", tags=["aptly-dashboard"])


@router.get("/summary")
def get_dashboard_summary_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_summary(session=session)


@router.get("/providers")
def get_dashboard_providers_endpoint(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_providers(session=session)


@router.get("/providers/{provider}/releases")
def get_dashboard_provider_releases_endpoint(
    provider: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_provider_releases(
        session=session,
        provider=provider,
    )


@router.get("/providers/{provider}/releases/{release}")
def get_dashboard_provider_release_detail_endpoint(
    provider: str,
    release: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_provider_release_detail(
        session=session,
        provider=provider,
        release=release,
    )


@router.get("/repositories")
def get_dashboard_repositories_endpoint(
    provider: str | None = Query(default=None),
    release: str | None = Query(default=None),
    health_status: str | None = Query(default=None),
    compliance_status: str | None = Query(default=None),
    operational_status: str | None = Query(default=None),
    retention_status: str | None = Query(default=None),
    only_non_compliant: bool = Query(default=False),
    search: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_repositories(
        session=session,
        provider=provider,
        release=release,
        health_status=health_status,
        compliance_status=compliance_status,
        operational_status=operational_status,
        retention_status=retention_status,
        only_non_compliant=only_non_compliant,
        search=search,
    )


@router.get("/repositories/by-name/{repo_name}")
def get_dashboard_repository_by_name_endpoint(
    repo_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_repository_by_name(
        session=session,
        repo_name=repo_name,
    )


@router.get("/repositories/{repo_id}")
def get_dashboard_repository_by_id_endpoint(
    repo_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_repository_by_id(
        session=session,
        repo_id=repo_id,
    )


@router.get("/compliance")
def get_dashboard_compliance_endpoint(
    provider: str | None = Query(default=None),
    release: str | None = Query(default=None),
    issue_code: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    return get_dashboard_compliance(
        session=session,
        provider=provider,
        release=release,
        issue_code=issue_code,
    )
