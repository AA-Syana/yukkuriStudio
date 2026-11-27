"""音声・画像・シナリオ解析の生成処理。AIエンジンは providers 経由でのみ呼ぶ。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..constants import EMOTIONS, SAMPLE_VOICE_TEXT
from ..models import Asset, Character, Dialogue, DialogueSuggestion, Project, Script
from ..providers.base import DialogueInput, ImageRequest, VoiceRequest
from ..providers.registry import Providers
from ..storage.local import LocalStorage
from .character_service import build_image_prompt, storage_prefix


class JobError(Exception):
    """ユーザーに見せてよいメッセージを持つ、ジョブ失敗の例外。"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- 音声 ----------------
def generate_voice(db: Session, storage: LocalStorage, providers: Providers, project: Project, dialogue: Dialogue) -> None:
    """1セリフ分の音声を(再)生成する。既存の音声は置き換える。声の設定は、このプロジェクトのキャラクター(コピー)のもの。"""
    voice_settings = dict(dialogue.character.voice_settings or {}) if dialogue.character else {}
    dialogue.generation_status = "generating"
    db.commit()
    try:
        result = providers.voice.synthesize(
            VoiceRequest(text=dialogue.text, voice_settings=voice_settings, emotion=dialogue.emotion)
        )
        rel_path = storage.save_bytes(project.id, "audio", result.ext, result.data)
    except Exception as e:
        dialogue.generation_status = "failed"
        db.commit()
        raise JobError(f"音声の生成に失敗しました: {e}") from e

    old = dialogue.audio_asset
    old_path = old.file_path if old else None
    if old:
        db.delete(old)
    db.add(
        Asset(
            dialogue_id=dialogue.id,
            asset_type="audio",
            file_path=rel_path,
            meta={
                # 生成時点の入力を覚えておき、後で変更されたら「古い音声」と判定する(Dialogue.audio_stale)
                "text": dialogue.text,
                "emotion": dialogue.emotion,
                "voice_settings": voice_settings,
                "duration_ms": result.duration_ms,
                "provider": providers.voice.name,
                "created_at": _now(),
            },
        )
    )
    dialogue.generation_status = "done"
    db.commit()
    db.expire(dialogue, ["assets"])
    if old_path:
        storage.delete(old_path)


def needs_voice(dialogue: Dialogue) -> bool:
    return dialogue.audio_asset is None or bool(dialogue.audio_stale)


# ---------------- 画像 ----------------
def replace_character_image(
    db: Session, storage: LocalStorage, character: Character, expression: str, rel_path: str, meta: dict
) -> None:
    """キャラクターの表情画像を登録する。同じ表情の既存画像があれば置き換える。"""
    old = next((a for a in character.assets if a.asset_type == "image" and a.meta.get("expression") == expression), None)
    old_path = old.file_path if old else None
    if old:
        db.delete(old)
    db.add(
        Asset(
            character_id=character.id,
            asset_type="image",
            file_path=rel_path,
            meta={"expression": expression, "created_at": _now(), **meta},
        )
    )
    db.commit()
    db.expire(character, ["assets"])
    if old_path:
        storage.delete(old_path)


def generate_image(
    db: Session, storage: LocalStorage, providers: Providers, character: Character, expression: str
) -> None:
    """ライブラリ・プロジェクト用コピーのどちらにも使える(保存先は storage_prefix が決める)。"""
    prompt = build_image_prompt(character)
    neutral = next((a for a in character.assets if a.asset_type == "image" and a.meta.get("expression") == "neutral"), None)
    # 「通常」以外は、登録済みの「通常」画像を参照させて外見の一貫性を保つ(F-24)
    reference = storage.absolute(neutral.file_path) if neutral and expression != "neutral" else None
    try:
        result = providers.image.generate(
            ImageRequest(
                prompt=prompt,
                character_name=character.name,
                expression=expression,
                seed=character.id,
                reference_path=reference,
            )
        )
        rel_path = storage.save_bytes(storage_prefix(character), "images", result.ext, result.data)
    except Exception as e:
        raise JobError(f"画像の生成に失敗しました: {e}") from e
    replace_character_image(
        db, storage, character, expression, rel_path,
        {"source": "generated", "prompt": prompt, "provider": providers.image.name},
    )


# ---------------- 音声サンプル(キャラクター画面の試聴用) ----------------
def generate_voice_sample(db: Session, storage: LocalStorage, providers: Providers, character: Character) -> None:
    voice_settings = dict(character.voice_settings or {})
    try:
        result = providers.voice.synthesize(
            VoiceRequest(text=SAMPLE_VOICE_TEXT, voice_settings=voice_settings, emotion="neutral")
        )
        rel_path = storage.save_bytes(storage_prefix(character), "audio", result.ext, result.data)
    except Exception as e:
        raise JobError(f"音声サンプルの生成に失敗しました: {e}") from e
    old = next((a for a in character.assets if a.asset_type == "voice_sample"), None)
    old_path = old.file_path if old else None
    if old:
        db.delete(old)
    db.add(
        Asset(
            character_id=character.id,
            asset_type="voice_sample",
            file_path=rel_path,
            meta={  # 声の設定を覚えておき、後で変更されたら「古いサンプル」と判定する(Character.voice_sample_stale)
                "text": SAMPLE_VOICE_TEXT,
                "voice_settings": voice_settings,
                "duration_ms": result.duration_ms,
                "provider": providers.voice.name,
                "created_at": _now(),
            },
        )
    )
    db.commit()
    db.expire(character, ["assets"])
    if old_path:
        storage.delete(old_path)


# ---------------- シナリオ解析 ----------------
def analyze_script(db: Session, providers: Providers, script: Script) -> None:
    """感情の推定と改善案の作成。ユーザーが手動編集したセリフの感情は上書きしない。"""
    project = script.project
    dialogues = list(script.dialogues)
    if not dialogues:
        raise JobError("解析するセリフがありません")
    characters = {c.id: c for c in project.characters}
    inputs = []
    for d in dialogues:
        c = characters.get(d.character_id) if d.character_id else None
        inputs.append(
            DialogueInput(
                dialogue_id=d.id,
                speaker_name=c.name if c else d.speaker_name,
                speaker_personality=c.personality if c else "",
                speaker_style=c.speaking_style if c else "",
                text=d.text,
            )
        )
    try:
        results = {r.dialogue_id: r for r in providers.llm.analyze(inputs)}
    except Exception as e:
        raise JobError(f"シナリオの解析に失敗しました: {e}") from e

    for d in dialogues:
        r = results.get(d.id)
        if r is None:
            continue
        if not d.is_user_edited and r.emotion in EMOTIONS:
            d.emotion = r.emotion
        if r.suggestion:
            if d.suggestion_row:
                d.suggestion_row.text = r.suggestion
            else:
                d.suggestion_row = DialogueSuggestion(text=r.suggestion)
        else:
            d.suggestion_row = None
    db.commit()
