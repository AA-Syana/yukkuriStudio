"""モックLLM: キーワードによる簡易な感情判定と、形式面の改善案。本物のLLMに差し替えるまでの仮実装。"""
from ..base import DialogueAnalysis, DialogueInput

# 先に書いたものが優先される
_EMOTION_KEYWORDS = (
    ("angry", ("怒", "ふざけ", "許さ", "ばか", "馬鹿", "うるさ", "むかつ")),
    ("surprised", ("えっ", "まじ", "マジ", "驚", "!?", "！？", "なんだと", "うそ", "嘘")),
    ("sad", ("悲", "残念", "つら", "辛", "泣", "寂し", "ごめん")),
    ("happy", ("嬉", "楽し", "ありがとう", "やった", "最高", "笑", "わーい", "ｗ", "w")),
)
LONG_TEXT_THRESHOLD = 60


def _emotion(text: str) -> str:
    for emotion, keywords in _EMOTION_KEYWORDS:
        if any(k in text for k in keywords):
            return emotion
    return "neutral"


def _suggestion(d: DialogueInput) -> str | None:
    if d.speaker_name is None:
        return "話者が未指定です。音声と立ち絵を付けるには話者を選んでください。"
    if len(d.text) > LONG_TEXT_THRESHOLD:
        return f"セリフが長め（{len(d.text)}文字）です。2つに分けると字幕が読みやすくなります。"
    if d.text.count("！") + d.text.count("!") >= 3:
        return "感嘆符が多めです。強調したい箇所に絞ると自然に聞こえます。"
    return None


class MockLLMProvider:
    name = "mock"

    def analyze(self, dialogues: list[DialogueInput]) -> list[DialogueAnalysis]:
        return [DialogueAnalysis(d.dialogue_id, _emotion(d.text), _suggestion(d)) for d in dialogues]
