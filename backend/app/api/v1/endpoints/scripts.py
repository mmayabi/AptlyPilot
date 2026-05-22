from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api.deps import get_db_session
from app.core.permissions import require_viewer
from app.models.user import User
from app.schemas.script import ScriptRead
from app.services.script_service import (
    list_scripts,
    get_script,
    script_to_read,
)

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.get("", response_model=list[ScriptRead])
def list_all_scripts(
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    scripts = list_scripts(session)
    return [script_to_read(script) for script in scripts]


@router.get("/{script_id}", response_model=ScriptRead)
def get_script_details(
    script_id: int,
    session: Session = Depends(get_db_session),
    current_user: User = Depends(require_viewer),
):
    script = get_script(script_id, session)
    return script_to_read(script)