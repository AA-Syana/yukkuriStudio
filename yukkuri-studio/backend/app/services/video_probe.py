"""ffprobeによる動画情報の取得。JSON解析部分は純粋関数にしてffprobe無しでテストできるようにしている。"""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


class VideoProbeError(Exception):
    pass


@dataclass
class VideoInfo:
    duration_ms: int
    width: int
    height: int
    fps: float | None


def _parse_fps(value: str | None) -> float | None:
    if not value or "/" not in value:
        return None
    num, den = value.split("/", 1)
    try:
        return round(float(num) / float(den), 3) if float(den) else None
    except ValueError:
        return None


def parse_probe_output(data: dict) -> VideoInfo:
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise VideoProbeError("映像ストリームが見つかりません")
    raw_duration = (data.get("format") or {}).get("duration") or video.get("duration")
    try:
        duration_ms = round(float(raw_duration) * 1000)
    except (TypeError, ValueError):
        raise VideoProbeError("動画の長さを取得できません")
    return VideoInfo(
        duration_ms=duration_ms,
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_parse_fps(video.get("avg_frame_rate")),
    )


def parse_has_audio(data: dict) -> bool:
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def probe_has_audio(path: Path, ffprobe: str = "ffprobe") -> bool:
    """動画に音声ストリームがあるか。調べられなければ False(元動画の音を混ぜずに書き出す)。"""
    cmd = [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-select_streams", "a", str(path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return result.returncode == 0 and parse_has_audio(json.loads(result.stdout))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def probe_video(path: Path) -> VideoInfo:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        raise VideoProbeError("ffprobe が見つかりません。FFmpegをインストールしてください")
    except subprocess.TimeoutExpired:
        raise VideoProbeError("動画の解析がタイムアウトしました")
    if result.returncode != 0:
        raise VideoProbeError("動画ファイルを解析できません。破損しているか非対応の形式です")
    return parse_probe_output(json.loads(result.stdout))
