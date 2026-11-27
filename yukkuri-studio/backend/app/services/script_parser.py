"""台本テキストのパーサー(規則ベース)。

書式(Ver.2.0):
    [霊夢]
    こんにちは！
    今日は実況をやります      ← 次の [話者] が出るまでの各行が、その話者のセリフ(1行=1セリフ)
    [魔理沙]
    よろしくな
    # コメント                ← 空行と # で始まる行は無視

互換: `[話者]` の行が1つも無い台本に限り、旧書式「話者: セリフ」(半角/全角コロン)も読む。
      `[話者]` がある台本では、「注意: ○○」のようなセリフ中のコロンを話者と誤認しないよう、旧書式は使わない。
同時会話は書式ではなく、画面上の操作で指定する。
"""
import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^\s*[\[［]\s*(.{1,30}?)\s*[\]］]\s*$")
_LEGACY_RE = re.compile(r"^\s*([^:：]{1,20}?)\s*[:：]\s*(.*\S)\s*$")


@dataclass
class ParsedLine:
    speaker: str | None
    text: str
    line_no: int  # 元テキストでの行番号(1始まり)。警告の表示に使う


def parse_scenario(content: str) -> list[ParsedLine]:
    rows = [(i, line.strip()) for i, line in enumerate(content.splitlines(), start=1)]
    rows = [(i, s) for i, s in rows if s and not s.startswith("#")]
    bracket_mode = any(_HEADER_RE.match(s) for _, s in rows)

    result: list[ParsedLine] = []
    speaker: str | None = None
    for line_no, stripped in rows:
        header = _HEADER_RE.match(stripped)
        if header:
            speaker = header.group(1).strip()
            continue
        if not bracket_mode:
            legacy = _LEGACY_RE.match(stripped)
            if legacy:
                speaker = legacy.group(1).strip()
                result.append(ParsedLine(speaker, legacy.group(2).strip(), line_no))
                continue
        result.append(ParsedLine(speaker, stripped, line_no))
    return result
