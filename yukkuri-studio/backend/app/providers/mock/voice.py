"""モック音声: 文字数に応じた長さの単純なサイン波WAVを作る。外部サービス不要。

実際の声ではないが、長さ・速度・声の高さの設定は反映されるので、
音声の長さ取得(F-31)やタイミング調整(Phase 3)を本物と同じ流れで開発できる。
"""
import io
import math
import struct
import wave
from typing import Any

from ..base import VoiceRequest, VoiceResult

SAMPLE_RATE = 16000
MS_PER_CHAR = 130
BASE_FREQ_HZ = 220.0


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class MockVoiceProvider:
    name = "mock"

    def synthesize(self, req: VoiceRequest) -> VoiceResult:
        speed = min(max(_number(req.voice_settings.get("speed"), 1.0), 0.25), 4.0)
        pitch = min(max(_number(req.voice_settings.get("pitch"), 0.0), -1.0), 1.0)  # ±1で±1オクターブ

        duration_ms = max(300, round(len(req.text) * MS_PER_CHAR / speed))
        freq = BASE_FREQ_HZ * (2**pitch)
        n = int(SAMPLE_RATE * duration_ms / 1000)
        fade = 400  # 先頭と末尾のプチ音を避けるフェード(サンプル数)
        samples = [
            int(3000 * min(1.0, i / fade, (n - i) / fade) * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
            for i in range(n)
        ]

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(struct.pack(f"<{n}h", *samples))
        return VoiceResult(data=buf.getvalue(), ext=".wav", duration_ms=round(n * 1000 / SAMPLE_RATE))
