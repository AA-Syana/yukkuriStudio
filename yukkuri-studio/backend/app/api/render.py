import shutil

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import GenerationJob, Project, Script, TimelineItem
from ..schemas import JobOut, RenderFileOut, RenderRequest, RenderStatusOut
from ..services.render import JOB_RENDER
from ..storage.local import LocalStorage
from .deps import get_project_or_404, get_storage
from .generation import JobContext, get_job_context

router = APIRouter(tags=["render"])


def _last_success(db: Session, project: Project, storage: LocalStorage) -> GenerationJob | None:
    """ダウンロードできる最新の書き出し(ファイルが実際に残っているもの)。"""
    jobs = db.scalars(select(GenerationJob).where(
        GenerationJob.project_id == project.id, GenerationJob.job_type == JOB_RENDER, GenerationJob.status == "succeeded"
    ).order_by(GenerationJob.created_at.desc()))
    for job in jobs:
        file = (job.result or {}).get("file")
        if file and storage.absolute(file).exists():
            return job
    return None


@router.post("/api/projects/{project_id}/render", response_model=JobOut, status_code=202)
def start_render(
    body: RenderRequest, project: Project = Depends(get_project_or_404), ctx: JobContext = Depends(get_job_context)
):
    """台本のタイムラインをMP4に書き出す。処理はバックグラウンドで進み、進捗は render-status で確認する。"""
    if body.script_id is not None:
        script = ctx.db.get(Script, body.script_id)
        if script is None or script.project_id != project.id:
            raise HTTPException(404, "台本が見つかりません")
    else:
        script = project.scripts[0] if project.scripts else None
        if script is None:
            raise HTTPException(422, "台本がありません")
    has_items = ctx.db.scalars(
        select(TimelineItem.id).where(TimelineItem.dialogue_id.in_([d.id for d in script.dialogues])).limit(1)
    ).first() if script.dialogues else None
    if has_items is None:
        raise HTTPException(422, "タイムラインが空です。動画編集画面で「タイミングを自動配置」を実行してください")
    if shutil.which(settings.ffmpeg_path) is None:
        raise HTTPException(503, "FFmpeg が見つかりません。インストールして PATH に追加するか、環境変数 FFMPEG_PATH を設定してください")
    params = {"height": body.height, "include_original_audio": body.include_original_audio,
              "original_volume": body.original_volume}
    return ctx.start(project.id, JOB_RENDER, script.id, params)


@router.get("/api/projects/{project_id}/render-status", response_model=RenderStatusOut)
def render_status(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)
):
    latest = db.scalars(select(GenerationJob).where(
        GenerationJob.project_id == project.id, GenerationJob.job_type == JOB_RENDER
    ).order_by(GenerationJob.created_at.desc())).first()
    done = _last_success(db, project, storage)
    last_success = None
    if done is not None:
        r = done.result or {}
        last_success = RenderFileOut(
            job_id=done.id, script_id=r.get("script_id", ""), finished_at=done.updated_at, size_bytes=r.get("size_bytes", 0),
            width=r.get("width", 0), height=r.get("height", 0), duration_ms=r.get("duration_ms", 0),
            warnings=r.get("warnings", []),
        )
    return RenderStatusOut(job=JobOut.model_validate(latest) if latest else None, last_success=last_success)


@router.get("/api/projects/{project_id}/download")
def download_render(
    project: Project = Depends(get_project_or_404), db: Session = Depends(get_db), storage: LocalStorage = Depends(get_storage)
):
    done = _last_success(db, project, storage)
    if done is None:
        raise HTTPException(404, "書き出し済みの動画がありません。先に「MP4を書き出す」を実行してください")
    return FileResponse(
        storage.absolute(done.result["file"]), media_type="video/mp4", filename=f"{project.title or 'video'}.mp4"
    )
