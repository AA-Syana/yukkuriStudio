"""台本のパース結果をDBに反映する。"""
from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Character, Dialogue, Script
from ..storage.local import LocalStorage
from .script_parser import parse_scenario


class ScriptConflict(Exception):
    """手動編集済みのセリフがあり、上書きの確認が必要。"""


@dataclass
class UnknownSpeaker:
    name: str
    count: int
    library_character_id: str | None


@dataclass
class ParseOutcome:
    unknown_speakers: list[UnknownSpeaker]
    speakerless_lines: int


def parse_and_store(db: Session, script: Script, storage: LocalStorage, force: bool = False) -> ParseOutcome:
    """content からセリフを作り直す。

    - 手動編集したセリフがある場合は、force=True でない限り上書きしない。
    - 話者名が、このプロジェクトのキャラクター名に一致すれば結びつける。一致しなければ speaker_name だけを残し、
      「未登録の話者」として警告に返す(キャラクターは自動では作らない)。
    """
    project = script.project
    existing = list(script.dialogues)
    if any(d.is_user_edited for d in existing) and not force:
        raise ScriptConflict()

    old_files = [a.file_path for d in existing for a in d.assets if a.file_path]  # 消えるセリフの音声
    for d in existing:
        db.delete(d)
    db.flush()

    by_name = {c.name: c for c in project.characters}
    lines = parse_scenario(script.content)
    unknown_count: Counter[str] = Counter()
    speakerless = 0
    for index, line in enumerate(lines):
        character = by_name.get(line.speaker) if line.speaker else None
        if line.speaker is None:
            speakerless += 1
        elif character is None:
            unknown_count[line.speaker] += 1
        db.add(
            Dialogue(
                script_id=script.id,
                character_id=character.id if character else None,
                speaker_name=line.speaker,
                order_index=index,
                text=line.text,
            )
        )
    script.version += 1
    db.commit()
    db.refresh(script)
    for path in old_files:  # DBの更新が成功してからファイルを消す
        storage.delete(path)

    library = {}
    if unknown_count:
        rows = db.scalars(
            select(Character).where(
                Character.user_id == project.user_id, Character.project_id.is_(None), Character.name.in_(unknown_count)
            )
        )
        library = {c.name: c.id for c in rows}
    return ParseOutcome(
        unknown_speakers=[UnknownSpeaker(n, c, library.get(n)) for n, c in unknown_count.items()],
        speakerless_lines=speakerless,
    )


def unknown_speakers_of(db: Session, script: Script) -> list[UnknownSpeaker]:
    """保存済みのセリフから、未登録の話者を数え直す(キャラクターを追加した後の警告の更新用)。"""
    counts: Counter[str] = Counter(
        d.speaker_name for d in script.dialogues if d.character_id is None and d.speaker_name
    )
    library = {}
    if counts:
        rows = db.scalars(
            select(Character).where(
                Character.user_id == script.project.user_id, Character.project_id.is_(None), Character.name.in_(counts)
            )
        )
        library = {c.name: c.id for c in rows}
    return [UnknownSpeaker(n, c, library.get(n)) for n, c in counts.items()]
