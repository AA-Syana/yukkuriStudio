import io
import wave

import pytest

from app.constants import EMOTIONS
from app.providers.base import DialogueInput, ImageRequest, VoiceRequest
from app.providers.mock.image import MockImageProvider
from app.providers.mock.llm import MockLLMProvider
from app.providers.mock.voice import MockVoiceProvider
from app.providers.registry import build_providers

def test_mock_voice_is_valid_wav_and_duration_matches():
    result = MockVoiceProvider().synthesize(VoiceRequest("こんにちは", {}, "neutral"))
    with wave.open(io.BytesIO(result.data)) as w:
        assert round(w.getnframes() * 1000 / w.getframerate()) == result.duration_ms
    assert result.ext == ".wav"


def test_mock_voice_speed_changes_duration():
    p = MockVoiceProvider()
    normal = p.synthesize(VoiceRequest("こんにちは、元気ですか", {}, "neutral"))
    fast = p.synthesize(VoiceRequest("こんにちは、元気ですか", {"speed": 2.0}, "neutral"))
    slow = p.synthesize(VoiceRequest("こんにちは、元気ですか", {"speed": 0.5}, "neutral"))
    assert fast.duration_ms < normal.duration_ms < slow.duration_ms


def test_mock_voice_tolerates_bad_settings():
    result = MockVoiceProvider().synthesize(VoiceRequest("あ", {"speed": "abc", "pitch": None}, "neutral"))
    assert result.duration_ms >= 300


def test_mock_image_varies_by_expression_and_is_stable_per_seed():
    p = MockImageProvider()
    make = lambda expr, seed="c1": p.generate(ImageRequest("赤いリボン", "霊夢", expr, seed)).data
    assert len({make(e) for e in EMOTIONS}) == len(EMOTIONS)  # 全表情が別の絵
    assert make("happy") == make("happy")  # 再現性
    assert make("happy", "c1") != make("happy", "c2")  # キャラクターごとに配色が違う

    result = p.generate(ImageRequest("赤いリボン", "霊夢", "happy", "c1"))
    assert result.ext == ".png" and result.data.startswith(b"\x89PNG")


def test_mock_image_is_a_valid_transparent_png_of_fixed_size():
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(MockImageProvider().generate(ImageRequest("", "霊夢", "neutral", "x")).data))
    assert img.size == (300, 450) and img.mode == "RGBA"
    assert img.getpixel((2, 2))[3] == 0  # 背景は透明(動画に重ねるため)
    assert img.getpixel((150, 150))[3] == 255  # 顔の部分は不透明


def test_mock_image_accepts_any_name_without_error():
    for name in ("", "<script>", "あ" * 40, "Name & \"quote\""):
        assert MockImageProvider().generate(ImageRequest("", name, "neutral", "x")).data.startswith(b"\x89PNG")


def _dlg(text, speaker="霊夢"):
    return DialogueInput("d1", speaker, "", "", text)


@pytest.mark.parametrize(
    "text,emotion",
    [("ありがとう、嬉しい！", "happy"), ("ふざけるな", "angry"), ("えっ！？", "surprised"), ("ごめんね…", "sad"), ("そうですね", "neutral")],
)
def test_mock_llm_emotion(text, emotion):
    assert MockLLMProvider().analyze([_dlg(text)])[0].emotion == emotion


def test_mock_llm_suggestions():
    llm = MockLLMProvider()
    assert "長め" in llm.analyze([_dlg("あ" * 61)])[0].suggestion
    assert "未指定" in llm.analyze([_dlg("こんにちは", speaker=None)])[0].suggestion
    assert llm.analyze([_dlg("こんにちは")])[0].suggestion is None


def test_registry_rejects_unknown_provider():
    with pytest.raises(ValueError):
        build_providers(voice="nope")
