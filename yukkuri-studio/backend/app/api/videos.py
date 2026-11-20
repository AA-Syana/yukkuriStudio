from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..core.config import settings
from ..core.database import get_db
from ..models import Project, Video
from ..schemas import VideoOut
from ..services.video_probe import VideoProbeError, probe_video
from ..storage.local import FileTooLarge, LocalStorage
from .deps import get_project_or_404, get_storage

router = APIRouter(prefix="/api/projects/{project_id}/video", tags=["videos"])

ALLOWED_EXTENSIONS = {".mp4"}  # 初期対応はMP4のみ


@router.post("", response_model=VideoOut, status_code=201)
def upload_video(
    file: UploadFile = File(...),
    project: Project = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
):
    filename = file.filename or "video.mp4"
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "MP4形式の動画のみアップロードできます")

    try:
        rel_path = storage.save_upload(project.id, "videos", ext, file.file, settings.max_upload_bytes)
    except FileTooLarge:
        raise HTTPException(413, "ファイルサイズが上限を超えています")

    try:
        info = probe_video(storage.absolute(rel_path))
    except VideoProbeError as e:
        storage.delete(rel_path)
        raise HTTPException(422, str(e))

    old_path = None
    if project.video is not None:  # 差し替え: 古い動画を置き換える
        old_path = project.video.file_path
        db.delete(project.video)
        db.flush()
    video = Video(
        project_id=project.id,
        original_filename=filename,
        file_path=rel_path,
        duration_ms=info.duration_ms,
        width=info.width,
        height=info.height,
        fps=info.fps,
    )
    db.add(video)
    db.commit()
    if old_path:
        storage.delete(old_path)
    return video


def _get_video_or_404(project: Project) -> Video:
    if project.video is None:
        raise HTTPException(404, "動画がまだアップロードされていません")
    return project.video


@router.get("", response_model=VideoOut)
def get_video(project: Project = Depends(get_project_or_404)):
    return _get_video_or_404(project)


@router.get("/stream")
def stream_video(
    project: Project = Depends(get_project_or_404),
    storage: LocalStorage = Depends(get_storage),
):
    video = _get_video_or_404(project)
    path = storage.absolute(video.file_path)
    if not path.exists():
        raise HTTPException(404, "動画ファイルが見つかりません")
    return FileResponse(path, media_type="video/mp4")
