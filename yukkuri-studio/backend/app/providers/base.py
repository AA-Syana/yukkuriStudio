"""AIエンジンの共通インターフェース。

サービス層はここで定義した型だけに依存する。モックでも実APIでも、このインターフェースを
満たすクラスを registry.py に登録すれば差し替えられる(N-07)。
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


# ---- 音声合成 ----
@dataclass
class VoiceRequest:
    text: str
    voice_settings: dict[str, Any]  # pitch / speed など。キャラクターごとの設定
    emotion: str


@dataclass
class VoiceResult:
    data: bytes
    ext: str  # ".wav" など
    duration_ms: int  # 生成した音声の長さ(Phase 3の時間配置で使う)


class VoiceProvider(Protocol):
    name: str

    def synthesize(self, req: VoiceRequest) -> VoiceResult: ...


# ---- 画像生成 ----
@dataclass
class ImageRequest:
    prompt: str  # キャラクターの外見設定の文章
    character_name: str
    expression: str  # constants.EMOTIONS のいずれか
    seed: str  # 同じキャラクターで常に同じ値。外見の一貫性(F-24)に使う
    reference_path: Path | None = None  # 登録済みの「通常」画像。あれば参照して一貫性を保つ


@dataclass
class ImageResult:
    data: bytes
    ext: str


class ImageProvider(Protocol):
    name: str

    def generate(self, req: ImageRequest) -> ImageResult: ...


# ---- シナリオ解析(LLM) ----
@dataclass
class DialogueInput:
    dialogue_id: str
    speaker_name: str | None
    speaker_personality: str
    speaker_style: str
    text: str


@dataclass
class DialogueAnalysis:
    dialogue_id: str
    emotion: str  # constants.EMOTIONS のいずれか
    suggestion: str | None = None  # 不自然な点の改善案(なければNone)


class LLMProvider(Protocol):
    name: str

    def analyze(self, dialogues: list[DialogueInput]) -> list[DialogueAnalysis]: ...
