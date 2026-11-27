"""設定名からプロバイダーを組み立てる。実APIのプロバイダーを足すときは辞書に1行追加する。"""
from dataclasses import dataclass

from .base import ImageProvider, LLMProvider, VoiceProvider
from .mock.image import MockImageProvider
from .mock.llm import MockLLMProvider
from .mock.voice import MockVoiceProvider

VOICE_PROVIDERS = {"mock": MockVoiceProvider}
IMAGE_PROVIDERS = {"mock": MockImageProvider}
LLM_PROVIDERS = {"mock": MockLLMProvider}


@dataclass
class Providers:
    voice: VoiceProvider
    image: ImageProvider
    llm: LLMProvider


def _pick(kind: str, table: dict, name: str):
    if name not in table:
        raise ValueError(f"{kind}プロバイダー「{name}」は未対応です。選べるもの: {', '.join(table)}")
    return table[name]()


def build_providers(voice: str = "mock", image: str = "mock", llm: str = "mock") -> Providers:
    return Providers(
        voice=_pick("音声", VOICE_PROVIDERS, voice),
        image=_pick("画像", IMAGE_PROVIDERS, image),
        llm=_pick("LLM", LLM_PROVIDERS, llm),
    )
