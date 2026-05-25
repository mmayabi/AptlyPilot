from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_admin, require_operator, require_viewer
from app.models.user import User
from app.schemas.repo import ConfigValidationResponse, RepoRead, RepoConfigRead, RepoSyncResponse
from app.services.repo_service import (
    get_all_repos,
    get_repo_config,
    get_repo_or_none,
    get_repos_by_provider,
    get_repos_by_provider_release,
    repo_to_read,
    sync_repos_from_config,
    validate_config_file,
)

router = APIRouter(prefix="/repos", tags=["repos"])


@router.get("", response_model=list[RepoRead])
def list_repositories(
    provider: str | None = Query(default=None),
    release: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    if provider and release:
        repos = get_repos_by_provider_release(session, provider, release)
    elif provider:
        repos = get_repos_by_provider(session, provider)
    else:
        repos = get_all_repos(session)

    return [repo_to_read(repo) for repo in repos]


@router.get("/{repo_name}", response_model=RepoRead)
def read_repository(
    repo_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    repo = get_repo_or_none(session, repo_name)
    if not repo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repo_name}",
        )
    return repo_to_read(repo)


@router.get("/{repo_name}/config", response_model=RepoConfigRead)
def read_repository_config(
    repo_name: str,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    repo_config = get_repo_config(session, repo_name)
    if not repo_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository not found: {repo_name}",
        )
    return repo_config


@router.post("/validate-config", response_model=ConfigValidationResponse)
def validate_repositories_config(current_user: User = Depends(require_operator)):
    return validate_config_file()


@router.post("/sync-from-config", response_model=RepoSyncResponse)
def sync_repositories_from_config(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_admin),
):
    result = validate_config_file()
    if not result.valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Invalid repository config", "errors": result.errors},
        )
    return sync_repos_from_config(session)