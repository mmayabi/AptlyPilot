from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models.script import Script
from app.schemas.script import ScriptRead


def script_to_read(script: Script) -> ScriptRead:
    return ScriptRead(
        id=script.id,
        name=script.name,
        description=script.description,
        params=script.params or {},
    )


def list_scripts(session: Session) -> list[Script]:
    return list(
        session.exec(
            select(Script).order_by(Script.id)
        ).all()
    )


def get_script(script_id: int, session: Session) -> Script:
    script = session.get(Script, script_id)
    if not script:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Script not found: {script_id}",
        )
    return script