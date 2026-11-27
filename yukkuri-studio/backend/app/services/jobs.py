"""生成ジョブの登録・実行。

今はFastAPIのBackgroundTasksで動かす。将来Celery等に移すときは、このファイルの
enqueue / run_job の呼び出し口だけを差し替えればよい(APIとサービス層は変えない)。

ジョブは必ず user_id を持つ。キャラクター単体の生成(画像・音声サンプル)はプロジェクトに属さないので
project_id は空でよい。実行時にも、対象が job.user_id のものか再確認する(APIでの確認の取りこぼし対策)。
"""
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..constants import EMOTIONS
from ..models import Character, Dialogue, GenerationJob, Script
from ..providers.registry import Providers
from ..storage.local import LocalStorage
from .generation import (
    JobError, analyze_script, generate_image, generate_voice, generate_voice_sample, needs_voice,
)
from .render import JOB_RENDER, render_job

# ジョブ種別。image:<表情> のように種別に表情を含める(DBにパラメータ列を増やさないため)
JOB_VOICE = "voice"  # target_id = dialogue_id
JOB_VOICE_ALL = "voice_all"  # target_id = script_id。音声が無い/古いセリフを全て生成
JOB_IMAGE_PREFIX = "image:"  # target_id = character_id
JOB_IMAGE_ALL = "image_all"  # target_id = character_id。全表情
JOB_VOICE_SAMPLE = "voice_sample"  # target_id = character_id
JOB_ANALYZE = "analyze"  # target_id = script_id

ACTIVE_STATUSES = ("queued", "running")


def enqueue(
    db: Session, user_id: str, project_id: str | None, job_type: str, target_id: str | None,
    params: dict | None = None,
) -> tuple[GenerationJob, bool]:
    """ジョブを登録する。同じ対象の実行中ジョブがあれば、二重に作らずそれを返す(2つ目はFalse)。"""
    existing = db.scalars(
        select(GenerationJob).where(
            GenerationJob.user_id == user_id,
            GenerationJob.job_type == job_type,
            GenerationJob.target_id == target_id,
            GenerationJob.status.in_(ACTIVE_STATUSES),
        )
    ).first()
    if existing:
        return existing, False
    job = GenerationJob(
        user_id=user_id, project_id=project_id, job_type=job_type, target_id=target_id, status="queued", params=params
    )
    db.add(job)
    db.commit()
    return job, True


def fail_interrupted_jobs(db: Session) -> None:
    """サーバー再起動などで途中のまま残ったジョブを失敗扱いにする(再実行できるようにする)。"""
    db.execute(
        update(GenerationJob)
        .where(GenerationJob.status.in_(ACTIVE_STATUSES))
        .values(status="failed", error="サーバーの再起動により中断されました。再実行してください")
    )
    db.commit()


def _set_progress(db: Session, job: GenerationJob, percent: int) -> None:
    job.progress = percent
    db.commit()


def _script(db: Session, job: GenerationJob) -> Script:
    s = db.get(Script, job.target_id) if job.target_id else None
    if s is None or s.project.user_id != job.user_id:
        raise JobError("対象の台本が見つかりません(削除された可能性があります)")
    return s


def _dialogue(db: Session, job: GenerationJob) -> Dialogue:
    d = db.get(Dialogue, job.target_id) if job.target_id else None
    if d is None or d.script.project.user_id != job.user_id:
        raise JobError("対象のセリフが見つかりません(削除された可能性があります)")
    return d


def _character(db: Session, job: GenerationJob) -> Character:
    c = db.get(Character, job.target_id) if job.target_id else None
    if c is None or c.user_id != job.user_id:
        raise JobError("対象のキャラクターが見つかりません(削除された可能性があります)")
    return c


def _dispatch(db: Session, storage: LocalStorage, providers: Providers, job: GenerationJob) -> None:
    jt = job.job_type

    if jt == JOB_VOICE:
        d = _dialogue(db, job)
        generate_voice(db, storage, providers, d.script.project, d)

    elif jt == JOB_VOICE_ALL:
        script = _script(db, job)
        targets = [d for d in script.dialogues if needs_voice(d)]
        failures: list[str] = []
        for i, d in enumerate(targets):
            try:
                generate_voice(db, storage, providers, script.project, d)
            except JobError as e:
                failures.append(str(e))
            _set_progress(db, job, round((i + 1) * 100 / len(targets)))
        if failures:  # 成功分は保存済み。再実行すると失敗分だけが対象になる
            raise JobError(f"{len(failures)}件の音声生成に失敗しました。{failures[0]}")

    elif jt.startswith(JOB_IMAGE_PREFIX):
        expression = jt[len(JOB_IMAGE_PREFIX):]
        if expression not in EMOTIONS:
            raise JobError(f"未対応の表情です: {expression}")
        generate_image(db, storage, providers, _character(db, job), expression)

    elif jt == JOB_IMAGE_ALL:
        character = _character(db, job)
        for i, expression in enumerate(EMOTIONS):  # neutralが先頭。後続の表情はこれを参照する
            generate_image(db, storage, providers, character, expression)
            _set_progress(db, job, round((i + 1) * 100 / len(EMOTIONS)))

    elif jt == JOB_VOICE_SAMPLE:
        generate_voice_sample(db, storage, providers, _character(db, job))

    elif jt == JOB_ANALYZE:
        analyze_script(db, providers, _script(db, job))

    elif jt == JOB_RENDER:
        render_job(db, storage, job, lambda pct: _set_progress(db, job, pct))

    else:
        raise JobError(f"未対応のジョブ種別です: {jt}")


def run_job(
    job_id: str,
    session_factory: Callable[[], Session],
    storage: LocalStorage,
    providers: Providers,
) -> None:
    """バックグラウンドで実行される。リクエストのセッションとは別のセッションを使う。"""
    db = session_factory()
    try:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return
        job.status, job.progress, job.error = "running", 0, None
        db.commit()
        try:
            _dispatch(db, storage, providers, job)
        except Exception as e:  # JobError以外の想定外のエラーも、ジョブの失敗として記録する
            db.rollback()
            job = db.get(GenerationJob, job_id)
            if job is None:  # 実行中にプロジェクトが削除されたなど
                return
            job.status = "failed"
            job.error = (str(e) or e.__class__.__name__)[:500]
            db.commit()
        else:
            job.status, job.progress = "succeeded", 100
            db.commit()
    finally:
        db.close()
