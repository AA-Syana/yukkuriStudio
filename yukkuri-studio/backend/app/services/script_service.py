"""シナリオのパース結果をDBに反映する。"""
from sqlalchemy.orm import Session

from ..models import Character, Dialogue, Project
from .script_parser import parse_scenario


class ScriptConflict(Exception):
    """手動編集済みのセリフがあり、上書きの確認が必要。"""


def parse_and_store(db: Session, project: Project, force: bool = False) -> list[Character]:
    """raw_textからセリフを作り直す。新規に作られたキャラクターのリストを返す。

    ユーザーが手動編集したセリフがある場合は、force=True でない限り上書きしない。
    """
    script = project.script
    assert script is not None
    existing = list(script.dialogues)
    if any(d.is_user_edited for d in existing) and not force:
        raise ScriptConflict()

    for d in existing:
        db.delete(d)
    db.flush()

    characters = {c.name: c for c in project.characters}
    created: list[Character] = []
    for index, line in enumerate(parse_scenario(script.raw_text)):
        character = None
        if line.speaker:
            character = characters.get(line.speaker)
            if character is None:  # 未登録の話者は空のキャラクターとして自動登録する
                character = Character(project_id=project.id, name=line.speaker, voice_settings={})
                db.add(character)
                db.flush()
                characters[line.speaker] = character
                created.append(character)
        db.add(
            Dialogue(
                script_id=script.id,
                character_id=character.id if character else None,
                order_index=index,
                text=line.text,
            )
        )
    script.version += 1
    db.commit()
    db.refresh(script)
    return created
