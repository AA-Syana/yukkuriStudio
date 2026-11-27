"""生成ジョブの起動と状態確認。起動APIは即座に202とジョブを返し、処理はバックグラウンドで進む。"""
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models import Character, Dialogue, GenerationJob, Project, Script, User
from ..providers.registry import Providers
from ..schemas import ImageGenerateRequest, JobOut, ProjectGenerateRequest
from ..services.jobs import (
    JOB_ANALYZE, JOB_IMAGE_ALL, JOB_IMAGE_PREFIX, JOB_VOICE, JOB_VOICE_ALL, JOB_VOICE_SAMPLE, enqueue, run_job,
)
from ..storage.local import LocalStorage
from .deps import (
    get_character_or_404, get_current_user, get_dialogue_or_404, get_job_or_404, get_project_or_404, get_providers,
    get_script_or_404, get_session_factory, get_storage,
)

router = APIRouter(tags=["generation"])


@dataclass
class JobContext:
    """ジョブ起動に必要な依存をまとめたもの。"""

    background: BackgroundTasks
    db: Session
    storage: LocalStorage
    providers: Providers
    session_factory: Callable[[], Session]
    user: User

    def start(
        self, project_id: str | None, job_type: str, target_id: str | None, params: dict | None = None
    ) -> GenerationJob:
        job, created = enqueue(self.db, self.user.id, project_id, job_type, target_id, params)
        if created:  # 同じ対象のジョブが実行中なら、新しく走らせずそのジョブを返す
            self.background.add_task(run_job, job.id, self.session_factory, self.storage, self.providers)
        return job


def get_job_context(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    providers: Providers = Depends(get_providers),
    session_factory: Callable[[], Session] = Depends(get_session_factory),
) -> JobContext:
    return JobContext(background, db, storage, providers, session_factory, user)


# ---------- 起動 ----------
@router.post("/api/dialogues/{dialogue_id}/regenerate", response_model=JobOut, status_code=202)
def regenerate_dialogue_voice(
    dialogue: Dialogue = Depends(get_dialogue_or_404), ctx: JobContext = Depends(get_job_context)
):
    """セリフ1件の音声を(再)生成する。"""
    return ctx.start(dialogue.script.project_id, JOB_VOICE, dialogue.id)


@router.post("/api/projects/{project_id}/generate", response_model=JobOut, status_code=202)
def generate_script_voices(
    body: ProjectGenerateRequest,
    project: Project = Depends(get_project_or_404),
    ctx: JobContext = Depends(get_job_context),
):
    """指定した台本のうち、音声が無い・生成後にセリフ/感情/声の設定が変わったセリフの音声をまとめて生成する。"""
    script = ctx.db.get(Script, body.script_id)
    if script is None or script.project_id != project.id:
        raise HTTPException(404, "台本が見つかりません")
    if not script.dialogues:
        raise HTTPException(422, "セリフがありません。先に台本をセリフに分割してください")
    return ctx.start(project.id, JOB_VOICE_ALL, script.id)


@router.post("/api/scripts/{script_id}/analyze", response_model=JobOut, status_code=202)
def analyze_script(script: Script = Depends(get_script_or_404), ctx: JobContext = Depends(get_job_context)):
    """台本を解析して、セリフごとの感情と改善案を作る。"""
    if not script.dialogues:
        raise HTTPException(422, "解析するセリフがありません")
    return ctx.start(script.project_id, JOB_ANALYZE, script.id)


@router.post("/api/characters/{character_id}/generate-image", response_model=JobOut, status_code=202)
def generate_character_images(
    body: ImageGenerateRequest,
    character: Character = Depends(get_character_or_404),
    ctx: JobContext = Depends(get_job_context),
):
    """外見設定から画像を生成する。表情を省略すると全表情を生成する。"""
    job_type = f"{JOB_IMAGE_PREFIX}{body.expression}" if body.expression else JOB_IMAGE_ALL
    return ctx.start(character.project_id, job_type, character.id)


@router.post("/api/characters/{character_id}/generate-voice", response_model=JobOut, status_code=202)
def generate_character_voice_sample(
    character: Character = Depends(get_character_or_404), ctx: JobContext = Depends(get_job_context)
):
    """声の設定で、サンプル音声を生成する(試聴用)。"""
    return ctx.start(character.project_id, JOB_VOICE_SAMPLE, character.id)


# ---------- 状態確認・再実行 ----------
@router.get("/api/generation-jobs", response_model=list[JobOut])
def list_jobs(
    project_id: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """自分の直近のジョブ。画面を開き直しても、進行中のジョブを追跡し直せるようにする。"""
    q = select(GenerationJob).where(GenerationJob.user_id == user.id)
    if project_id:
        q = q.where(GenerationJob.project_id == project_id)
    return db.scalars(q.order_by(GenerationJob.created_at.desc()).limit(30)).all()


@router.get("/api/generation-jobs/{job_id}", response_model=JobOut)
def get_job(job: GenerationJob = Depends(get_job_or_404)):
    return job


@router.post("/api/generation-jobs/{job_id}/retry", response_model=JobOut, status_code=202)
def retry_job(job: GenerationJob = Depends(get_job_or_404), ctx: JobContext = Depends(get_job_context)):
    """失敗したジョブをやり直す。音声の一括生成は、失敗した分だけが対象になる。"""
    if job.status != "failed":
        raise HTTPException(409, "失敗したジョブだけ再実行できます")
    job.status, job.progress, job.error = "queued", 0, None
    ctx.db.commit()
    ctx.background.add_task(run_job, job.id, ctx.session_factory, ctx.storage, ctx.providers)
    return job
