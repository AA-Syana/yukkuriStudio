"""MP4書き出しのジョブ処理。DBの内容(台本・タイムライン・素材)から RenderSpec を作り、render_core で書き出す。"""
import shutil
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import TRACK_AUDIO, TRACK_CHARACTER, TRACK_SUBTITLE
from ..core.config import settings
from ..fonts import find_font
from ..models import Character, GenerationJob, Script, TimelineItem
from ..storage.local import LocalStorage
from .generation import JobError
from .render_core import RenderError, render_to_file
from .render_plan import AudioClip, CharacterLayer, RenderSpec, SubtitleLayer, output_size, pick_image
from .video_probe import probe_has_audio

JOB_RENDER = "render"  # target_id = script_id
DEFAULT_FPS = 30.0
MAX_FPS = 60.0


def _character_images(storage: LocalStorage, character: Character) -> tuple[dict[str, str], int]:
    """表情 -> 画像ファイルのパス。使えない画像(ファイルが無い・SVG)は含めず、その数を返す。"""
    images: dict[str, str] = {}
    unusable = 0
    for a in character.assets:
        if a.asset_type != "image" or not a.file_path:
            continue
        path = storage.absolute(a.file_path)
        if path.suffix.lower() == ".svg" or not path.exists():
            unusable += 1  # SVGはPillowで読めない(以前のモック画像)。画像を作り直すとPNGになる
            continue
        images[a.meta.get("expression", "")] = str(path)
    return images, unusable


def build_spec(db: Session, storage: LocalStorage, script: Script, params: dict) -> tuple[RenderSpec, list[str]]:
    dialogues = list(script.dialogues)  # order_index順
    by_id = {d.id: d for d in dialogues}
    items = list(db.scalars(select(TimelineItem).where(TimelineItem.dialogue_id.in_(list(by_id))))) if by_id else []
    if not items:
        raise JobError("タイムラインが空です。先に「タイミングを自動配置」を実行してください")
    items.sort(key=lambda i: (by_id[i.dialogue_id].order_index, i.track_type))

    project = script.project
    video = project.video
    video_path = storage.absolute(video.file_path) if video else None
    if video_path is not None and not video_path.exists():
        raise JobError("元動画のファイルが見つかりません。アップロードし直してください")

    warnings: list[str] = []
    total_ms = max(max(i.end_ms for i in items), video.duration_ms if video else 0)
    width, height = output_size(video.width if video else None, video.height if video else None, params.get("height"))
    fps = min(video.fps or DEFAULT_FPS, MAX_FPS) if video else DEFAULT_FPS

    char_cache: dict[str, tuple[Character | None, dict[str, str]]] = {}
    unusable_images = 0
    missing_images = 0
    characters: list[CharacterLayer] = []
    subtitles: list[SubtitleLayer] = []
    audio: list[AudioClip] = []
    for item in items:
        d = by_id[item.dialogue_id]
        if item.track_type == TRACK_CHARACTER:
            if d.character_id not in char_cache:
                c = db.get(Character, d.character_id) if d.character_id else None
                images, bad = _character_images(storage, c) if c else ({}, 0)
                unusable_images += bad
                char_cache[d.character_id or ""] = (c, images)
            c, images = char_cache[d.character_id or ""]
            path = pick_image(images, item.expression, d.emotion)
            if path is None:
                missing_images += 1
            characters.append(CharacterLayer(
                item.start_ms, item.end_ms, item.position_x, item.position_y, item.scale, path,
                c.name if c else (d.speaker_name or ""),
            ))
        elif item.track_type == TRACK_SUBTITLE:
            subtitles.append(SubtitleLayer(
                item.start_ms, item.end_ms, item.position_x, item.position_y, item.font_size,
                item.text_override if item.text_override is not None else d.text,
            ))
        elif item.track_type == TRACK_AUDIO and d.audio_asset is not None and d.audio_asset.file_path:
            path = storage.absolute(d.audio_asset.file_path)
            if path.exists():
                audio.append(AudioClip(str(path), item.start_ms, item.end_ms, item.volume, item.playback_speed))

    silent = sum(1 for d in dialogues if d.audio_asset is None)
    if silent:
        warnings.append(f"{silent}件のセリフは音声が未生成のため、無音で書き出しました。")
    stale = sum(1 for d in dialogues if d.audio_stale)
    if stale:
        warnings.append(f"{stale}件のセリフは音声が古い(セリフ・感情・声の設定の変更前の音声)まま書き出しました。")
    unplaced = sum(1 for d in dialogues if d.start_ms is None or d.end_ms is None)
    if unplaced:
        warnings.append(f"{unplaced}件のセリフは時間が未配置のため、含まれていません。")
    if missing_images or unusable_images:
        warnings.append(
            f"立ち絵の画像が無い/使えない箇所があり、仮の枠で書き出しました(画像なし {missing_images}件、"
            f"使えない画像 {unusable_images}枚。以前のSVG画像は書き出しに使えないので、画像を再生成してください)。"
        )

    font = find_font(settings.render_font_path)
    if font is None and (subtitles or any(c.image_path is None for c in characters)):
        raise JobError("字幕用の日本語フォントが見つかりません。環境変数 RENDER_FONT_PATH にフォント(.ttf/.ttc)のパスを指定してください")

    spec = RenderSpec(
        width=width, height=height, fps=fps, total_ms=total_ms,
        video_path=str(video_path) if video_path else None, video_duration_ms=video.duration_ms if video else None,
        video_has_audio=bool(video_path and probe_has_audio(video_path)),
        include_original_audio=bool(params.get("include_original_audio", True)),
        original_volume=float(params.get("original_volume", 1.0)),
        characters=characters, subtitles=subtitles, audio=audio, font_path=font,
    )
    return spec, warnings


def render_job(db: Session, storage: LocalStorage, job: GenerationJob, on_progress) -> None:
    script = db.get(Script, job.target_id) if job.target_id else None
    if script is None or script.project.user_id != job.user_id:  # 実行時にも所有者を再確認する
        raise JobError("対象の台本が見つかりません(削除された可能性があります)")
    project = script.project
    spec, warnings = build_spec(db, storage, script, job.params or {})

    workdir = Path(tempfile.mkdtemp(prefix="yukkuri-render-"))
    try:
        output = workdir / "out.mp4"
        last = [-1]

        def progress(pct: int) -> None:
            if pct != last[0]:  # 値が変わったときだけDBへ書く
                last[0] = pct
                on_progress(pct)

        try:
            render_to_file(spec, workdir / "work", output, settings.ffmpeg_path, progress)
        except RenderError as e:
            raise JobError(str(e))
        size = output.stat().st_size
        rel = storage.adopt_file(project.id, "renders", ".mp4", output)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # 新しい書き出しができたので、古い書き出しファイルを消す(最新の1つだけ残す)
    for old in db.scalars(select(GenerationJob).where(
        GenerationJob.project_id == project.id, GenerationJob.job_type == JOB_RENDER, GenerationJob.id != job.id
    )):
        if old.result and old.result.get("file"):
            storage.delete(old.result["file"])
            old.result = {**old.result, "file": None}
    job.result = {
        "file": rel, "size_bytes": size, "script_id": script.id, "width": spec.width, "height": spec.height,
        "duration_ms": spec.total_ms, "warnings": warnings,
    }
    db.commit()
