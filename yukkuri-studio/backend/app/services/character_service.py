"""キャラクターの作成・コピー・削除。

方針(ユーザー決定): プロジェクトの編集画面でのキャラクターの状態を優先する。
キャラクター管理画面(ライブラリ)での編集は、次にプロジェクトへ追加するときから反映される。
そのため、プロジェクトへ追加する時点でライブラリの内容を「コピー」し、以降は別物として扱う。
"""
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..constants import APPEARANCE_FIELDS
from ..models import Asset, Character, Dialogue, Project, Script, User
from ..storage.local import LocalStorage


class NameConflict(Exception):
    pass


def storage_prefix(character: Character) -> str:
    """このキャラクターのファイルを置く場所。プロジェクトのコピーはプロジェクト配下に置く
    (プロジェクトを削除するとき、まとめて消えるようにするため)。"""
    if character.project_id:
        return f"{character.project_id}/characters/{character.id}"
    return f"characters/{character.id}"


def build_image_prompt(character: Character) -> str:
    """外見の入力項目と自由記述を、画像生成AIへ渡す1つの文章にまとめる。"""
    parts = []
    details = character.appearance_details or {}
    for key, label in APPEARANCE_FIELDS.items():
        value = (details.get(key) or "").strip()
        if value:
            parts.append(f"{label}: {value}")
    if character.appearance.strip():
        parts.append(character.appearance.strip())
    return "、".join(parts)


def _name_taken(db: Session, user_id: str, project_id: str | None, name: str, exclude_id: str | None) -> bool:
    q = select(Character.id).where(Character.user_id == user_id, Character.name == name)
    q = q.where(Character.project_id == project_id) if project_id else q.where(Character.project_id.is_(None))
    if exclude_id:
        q = q.where(Character.id != exclude_id)
    return db.scalar(q) is not None


def create_library_character(db: Session, user: User, data: dict) -> Character:
    if _name_taken(db, user.id, None, data["name"], None):
        raise NameConflict()
    character = Character(user_id=user.id, **data)
    db.add(character)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise NameConflict()
    return character


def update_character(db: Session, character: Character, changes: dict) -> Character:
    if "name" in changes and _name_taken(db, character.user_id, character.project_id, changes["name"], character.id):
        raise NameConflict()
    for key, value in changes.items():
        setattr(character, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise NameConflict()
    return character


def delete_library_character(db: Session, storage: LocalStorage, character: Character) -> None:
    """ライブラリから削除する。プロジェクト内のコピーには影響しない(コピー側の source_character_id が空になるだけ)。"""
    prefix = storage_prefix(character)
    db.delete(character)
    db.commit()
    storage.delete_tree(prefix)


def add_character_to_project(
    db: Session, storage: LocalStorage, project: Project, source: Character
) -> tuple[Character, bool]:
    """ライブラリのキャラクターを、今の内容でコピーしてプロジェクトに加える。(コピー, 新規作成したか) を返す。

    同じキャラクターを既に追加済みなら、何もせず既存のコピーを返す(ライブラリの更新を取り込み直したい場合は、
    一度プロジェクトから外して追加し直す)。
    """
    existing = next((c for c in project.characters if c.source_character_id == source.id), None)
    if existing:
        return existing, False
    if any(c.name == source.name for c in project.characters):
        raise NameConflict()

    copy = Character(
        user_id=source.user_id,
        project_id=project.id,
        source_character_id=source.id,
        name=source.name,
        description=source.description,
        personality=source.personality,
        appearance=source.appearance,
        appearance_details=dict(source.appearance_details or {}),
        speaking_style=source.speaking_style,
        voice_settings=dict(source.voice_settings or {}),
    )
    db.add(copy)
    db.flush()  # copy.id を確定させる(ファイルの置き場所に使う)

    prefix = storage_prefix(copy)
    copied_files: list[str] = []
    try:
        for asset in source.assets:
            if not asset.file_path:
                continue
            new_path = storage.copy_file(asset.file_path, prefix, "images" if asset.asset_type == "image" else "audio")
            copied_files.append(new_path)
            db.add(Asset(character_id=copy.id, asset_type=asset.asset_type, file_path=new_path, meta=dict(asset.meta)))

        # 台本に話者名だけ書かれていて、キャラクター未登録だったセリフを、このキャラクターに結びつける
        script_ids = select(Script.id).where(Script.project_id == project.id)
        db.execute(
            update(Dialogue)
            .where(Dialogue.script_id.in_(script_ids), Dialogue.character_id.is_(None), Dialogue.speaker_name == copy.name)
            .values(character_id=copy.id)
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_tree(prefix)
        raise
    db.refresh(copy)  # 画像のコピー分も含めて読み込み直す
    db.refresh(project)
    return copy, True


def remove_character_from_project(db: Session, storage: LocalStorage, character: Character) -> None:
    """プロジェクトからキャラクターを外す。セリフは消さず、話者を「未登録」に戻す(speaker_name は残る)。"""
    prefix = storage_prefix(character)
    db.execute(update(Dialogue).where(Dialogue.character_id == character.id).values(character_id=None))
    db.delete(character)
    db.commit()
    storage.delete_tree(prefix)
