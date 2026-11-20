"""シナリオテキストのパーサー(Phase 1は単純な規則ベース。AI解析はPhase 2で別サービスとして追加する)。

書式:
    霊夢: こんにちは！        ← 「話者: セリフ」(半角/全角コロン可)
    続きのセリフ              ← 話者なしの行は直前の話者を引き継ぐ
    # コメント                ← 空行と # で始まる行は無視
同時会話は書式ではなく、画面上の操作で指定する。
"""
import re
from dataclasses import dataclass

_LINE_RE = re.compile(r"^\s*([^:：]{1,20}?)\s*[:：]\s*(.*\S)\s*$")


@dataclass
class ParsedLine:
    speaker: str | None
    text: str


def parse_scenario(raw_text: str) -> list[ParsedLine]:
    result: list[ParsedLine] = []
    last_speaker: str | None = None
    for line in raw_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _LINE_RE.match(stripped)
        if match:
            last_speaker = match.group(1).strip()
            result.append(ParsedLine(last_speaker, match.group(2).strip()))
        else:
            result.append(ParsedLine(last_speaker, stripped))
    return result
