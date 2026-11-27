from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Project, Script
from ..schemas import ParseRequest, ParseResult, ScriptCreate, ScriptOut, ScriptUpdate
from ..services.script_service import ScriptConflict, parse_and_store
from ..storage.local import LocalStorage
from .deps import get_project_or_404, get_script_or_404, get_storage

router = APIRouter(tags=["scripts"])


@router.get("/api/projects/{project_id}/scripts", response_model=list[ScriptOut])
def list_scripts(project: Project = Depends(get_project_or_404)):
    return project.scripts


@router.post("/api/projects/{project_id}/scripts", response_model=ScriptOut, status_code=201)
def create_script(
    body: ScriptCreate, project: Project = Depends(get_project_or_404), db: Session = Depends(get_db)
):
    title = body.title.strip() or f"台本{len(project.scripts) + 1}"
    script = Script(project_id=project.id, title=title, content=body.content)
    db.add(script)
    db.commit()
    return script


@router.get("/api/scripts/{script_id}", response_model=ScriptOut)
def get_script(script: Script = Depends(get_script_or_404)):
    return script


@router.put("/api/scripts/{script_id}", response_model=ScriptOut)
def update_script(body: ScriptUpdate, script: Script = Depends(get_script_or_404), db: Session = Depends(get_db)):
    """タイトル・本文を保存するだけ。セリフへの分割は /parse で明示的に行う(手動編集を守るため)。"""
    if body.title is not None:
        script.title = body.title.strip() or script.title
    if body.content is not None:
        script.content = body.content
    db.commit()
    return script


@router.delete("/api/scripts/{script_id}", status_code=204)
def delete_script(
    script: Script = Depends(get_script_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    files = [a.file_path for d in script.dialogues for a in d.assets if a.file_path]
    db.delete(script)
    db.commit()
    for path in files:
        storage.delete(path)


@router.post("/api/scripts/{script_id}/parse", response_model=ParseResult)
def parse_script(
    body: ParseRequest,
    script: Script = Depends(get_script_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    try:
        outcome = parse_and_store(db, script, storage, force=body.force)
    except ScriptConflict:
        raise HTTPException(409, "手動で編集したセリフがあります。上書きする場合は確認してください")
    return ParseResult(
        dialogues=script.dialogues,
        unknown_speakers=outcome.unknown_speakers,
        speakerless_lines=outcome.speakerless_lines,
    )
