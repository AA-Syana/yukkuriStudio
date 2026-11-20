from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Project
from ..schemas import ParseRequest, ParseResult, ScriptOut, ScriptUpdate
from ..services.script_service import ScriptConflict, parse_and_store
from .deps import get_project_or_404

router = APIRouter(prefix="/api/projects/{project_id}/script", tags=["scripts"])


@router.get("", response_model=ScriptOut)
def get_script(project: Project = Depends(get_project_or_404)):
    return project.script


@router.put("", response_model=ScriptOut)
def save_script(
    body: ScriptUpdate,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    """テキストを保存するだけ。セリフへの分割は /parse で明示的に行う(手動編集を守るため)。"""
    project.script.raw_text = body.raw_text
    db.commit()
    return project.script


@router.post("/parse", response_model=ParseResult)
def parse_script(
    body: ParseRequest,
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
):
    try:
        created = parse_and_store(db, project, force=body.force)
    except ScriptConflict:
        raise HTTPException(409, "手動で編集したセリフがあります。上書きする場合は確認してください")
    return ParseResult(dialogues=project.script.dialogues, created_characters=created)
