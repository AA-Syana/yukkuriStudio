"""MP4書き出し。前半は純粋な計画の確認、後半は実際にFFmpegでMP4を作って中身を確かめる
(FFmpeg・日本語フォントが無い環境では後半を読み飛ばす)。"""
import io
import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from app.fonts import find_font
from app.providers.base import ImageRequest, VoiceRequest
from app.providers.mock.image import MockImageProvider
from app.providers.mock.voice import MockVoiceProvider
from app.services.render_core import RenderError, render_to_file
from app.services.render_plan import (
    AudioClip, CharacterLayer, RenderSpec, SubtitleLayer, audio_filter, build_segments, concat_list, output_size,
    parse_progress_line, pick_image, subtitle_levels, video_filter,
)

# ---------------- 純粋な計画 ----------------


def test_output_size_keeps_aspect_and_is_even():
    assert output_size(1920, 1080, None) == (1920, 1080)
    assert output_size(1920, 1080, 720) == (1280, 720)
    assert output_size(1280, 720, 480) == (854, 480)  # 853.3 → 偶数に丸める
    assert output_size(None, None, None) == (1920, 1080)
    assert output_size(None, None, 480) == (854, 480)
    assert output_size(1001, 563, None)[0] % 2 == 0 and output_size(1001, 563, None)[1] % 2 == 0


def test_segments_cover_everything_and_merge_equal_neighbors():
    segs = build_segments([(1000, 3000), (2000, 4000)], 5000)
    assert [(s.start_ms, s.end_ms, s.active) for s in segs] == [
        (0, 1000, ()), (1000, 2000, (0,)), (2000, 3000, (0, 1)), (3000, 4000, (1,)), (4000, 5000, ()),
    ]
    assert build_segments([], 2000)[0].start_ms == 0 and build_segments([], 2000)[-1].end_ms == 2000
    # 同じ表示が続くなら1つにまとめる(連続する2つのレイヤーの境目は、表示が変わるので分かれる)
    assert len(build_segments([(0, 1000), (1000, 2000)], 2000)) == 2
    # 範囲外にはみ出す項目は、全体の長さで切る
    assert build_segments([(500, 9000)], 2000)[-1].end_ms == 2000


def test_subtitle_levels_and_image_pick():
    assert subtitle_levels([(0.5, 0.9), (0.5, 0.9), (0.2, 0.5), (0.51, 0.89)]) == [0, 1, 0, 2]
    imgs = {"neutral": "n", "sad": "s"}
    assert pick_image(imgs, "sad", "happy") == "s" and pick_image(imgs, None, "sad") == "s"
    assert pick_image(imgs, "angry", "happy") == "n" and pick_image({"sad": "s"}, None, "happy") == "s"
    assert pick_image({}, None, "happy") is None


def test_concat_list_repeats_last_file():
    text = concat_list([("a.png", 1.5), ("b.png", 0.25)])
    assert text.splitlines() == ["ffconcat version 1.0", "file 'a.png'", "duration 1.500", "file 'b.png'", "duration 0.250", "file 'b.png'"]


def test_progress_line_parsing():
    assert parse_progress_line("out_time_us=1500000\n") == 1500
    assert parse_progress_line("out_time_ms=2500000") == 2500
    assert parse_progress_line("out_time_us=N/A") is None and parse_progress_line("progress=continue") is None
    assert parse_progress_line("out_time_us=-5") == 0


def _spec(**kw):
    base = dict(width=640, height=360, fps=30, total_ms=3000)
    base.update(kw)
    return RenderSpec(**base)


def test_filter_graphs_reflect_the_edit_settings():
    spec = _spec(
        video_path="v.mp4", video_duration_ms=2000, video_has_audio=True, original_volume=0.5,
        audio=[AudioClip("a.wav", 1200, 2200, 0.8, 1.5), AudioClip("b.wav", 0, 500, 1.0, 1.0)],
    )
    v = video_filter(spec)
    assert "scale=640:360" in v and "tpad=stop_mode=clone:stop_duration=1" in v and "overlay" in v  # 動画より長い分は最後の画面を保つ
    a = audio_filter(spec, ["a0.wav", "a1.wav"])
    assert "atempo=1.5" in a and "volume=0.8" in a and "adelay=1200:all=1" in a and "atrim=duration=1" in a
    assert "atempo" not in a.split("[a1]")[0].split("amovie=a1.wav")[1]  # 等速の音声には、速度変更を入れない
    assert "[a_orig]" in a and "volume=0.5" in a and "amix=inputs=4:" in a
    assert "[a_orig]" not in audio_filter(_spec(video_path="v.mp4", video_has_audio=True, include_original_audio=False), [])
    assert "tpad" not in video_filter(_spec(total_ms=2000, video_path="v.mp4", video_duration_ms=2000))


# ---------------- 実際にFFmpegで書き出す ----------------
FONT = find_font()
pytestmark_e2e = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None or FONT is None,
    reason="FFmpeg または日本語フォントが無い環境",
)
BG = (0x20, 0x60, 0xA0)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def _probe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    return json.loads(out)


def _frame(path: Path, seconds: float, tmp: Path) -> Image.Image:
    png = tmp / f"frame_{seconds}.png"
    _ffmpeg("-ss", str(seconds), "-i", str(path), "-frames:v", "1", str(png))
    return Image.open(png).convert("RGB")


def _rms_windows(path: Path, tmp: Path, windows: list[tuple[float, float]]) -> list[float]:
    wav = tmp / "audio_dump.wav"
    _ffmpeg("-i", str(path), "-vn", "-ac", "1", "-ar", "16000", str(wav))
    with wave.open(str(wav)) as w:
        rate, data = w.getframerate(), w.readframes(w.getnframes())
    samples = [int.from_bytes(data[i:i + 2], "little", signed=True) / 32768 for i in range(0, len(data) - 1, 2)]
    out = []
    for a, b in windows:
        part = samples[int(a * rate):int(b * rate)]
        out.append((sum(x * x for x in part) / max(len(part), 1)) ** 0.5)
    return out


@pytest.fixture
def assets(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(MockVoiceProvider().synthesize(VoiceRequest("こんにちは、テストです", {}, "neutral")).data)
    face = tmp_path / "face.png"
    face.write_bytes(MockImageProvider().generate(ImageRequest("", "霊夢", "happy", "s")).data)
    video = tmp_path / "src.mp4"  # 単色の映像 + 常に鳴っている440Hzの音(3秒)
    _ffmpeg("-f", "lavfi", "-i", f"color=c=0x2060a0:s=320x180:r=15:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(video))
    return {"voice": voice, "face": face, "video": video, "dir": tmp_path}


def _render(spec, tmp_path) -> Path:
    out = tmp_path / "out.mp4"
    progress: list[int] = []
    render_to_file(spec, tmp_path / "work", out, on_progress=progress.append)
    assert progress and progress[-1] == 100 and progress == sorted(progress)  # 進捗は増えるだけで、最後は100
    return out


def _white(img: Image.Image) -> int:
    """ほぼ白の画素の数(字幕の文字は白、背景は青や黒なので区別できる)。"""
    return sum(img.convert("L").histogram()[236:])


def _close(rgb, target, tol=24):
    return all(abs(a - b) <= tol for a, b in zip(rgb, target))


@pytestmark_e2e
def test_render_with_source_video_overlays_and_audio(assets):
    d = assets["dir"]
    spec = RenderSpec(
        width=640, height=360, fps=15, total_ms=3000, video_path=str(assets["video"]), video_duration_ms=3000,
        video_has_audio=True, include_original_audio=False, font_path=FONT,
        characters=[CharacterLayer(500, 2500, 0.5, 0.4, 1.0, str(assets["face"]), "霊夢")],  # 字幕(下部)と重ならない高さ
        subtitles=[SubtitleLayer(1000, 2000, 0.5, 0.9, 40, "字幕のテスト")],
        audio=[AudioClip(str(assets["voice"]), 1000, 2000, 1.0, 1.0)],
    )
    out = _render(spec, d)
    info = _probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert (v["width"], v["height"]) == (640, 360) and v["pix_fmt"] == "yuv420p"
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert abs(float(info["format"]["duration"]) - 3.0) < 0.15

    # 立ち絵: 0.2秒には無く、0.7秒には顔の色が出る(立ち絵の高さ=画面の0.6倍、顔の中心は画像の上から150/450)
    before, during = _frame(out, 0.2, d), _frame(out, 0.7, d)
    sprite_h = 360 * 0.6
    face_xy = (320, round(360 * 0.4 - sprite_h / 2 + sprite_h * (150 / 450)))
    assert _close(before.getpixel(face_xy), BG) and not _close(during.getpixel(face_xy), BG)
    # 字幕: 1.5秒の画面下部に白い文字の画素があり、0.7秒と2.5秒には無い
    def white_pixels(img):
        return _white(img.crop((160, int(360 * 0.9 - 30), 480, int(360 * 0.9 + 30))))
    assert white_pixels(_frame(out, 1.5, d)) > 40
    assert white_pixels(during) < 5 and white_pixels(_frame(out, 2.7, d)) < 5
    assert _close(_frame(out, 2.8, d).getpixel(face_xy), BG)  # 立ち絵は2.5秒で消える

    # 音声: 元動画の音を切っているので、セリフの区間(1.0〜2.0秒)だけ音がある
    quiet_before, talking, quiet_after = _rms_windows(out, d, [(0.1, 0.9), (1.1, 1.6), (2.2, 2.9)])
    assert talking > 0.02 and quiet_before < 0.003 and quiet_after < 0.003


@pytestmark_e2e
def test_render_audio_settings_original_sound_volume_and_speed(assets):
    d = assets["dir"]
    common = dict(width=320, height=180, fps=15, total_ms=3000, video_path=str(assets["video"]), video_duration_ms=3000,
                  video_has_audio=True, font_path=FONT)
    clip = lambda **kw: AudioClip(str(assets["voice"]), 1000, 2000, kw.get("volume", 1.0), kw.get("speed", 1.0))

    loud = _rms_windows(_render(RenderSpec(**common, include_original_audio=False, audio=[clip(volume=1.0)]), d), d, [(1.1, 1.6)])[0]
    quiet = _rms_windows(_render(RenderSpec(**common, include_original_audio=False, audio=[clip(volume=0.5)]), d), d, [(1.1, 1.6)])[0]
    assert 0.35 < quiet / loud < 0.65  # 音量50%なら、およそ半分

    with_orig = _rms_windows(_render(RenderSpec(**common, include_original_audio=True, original_volume=1.0), d), d, [(0.1, 0.9)])[0]
    muted_orig = _rms_windows(_render(RenderSpec(**common, include_original_audio=True, original_volume=0.0), d), d, [(0.1, 0.9)])[0]
    assert with_orig > 0.05 and muted_orig < 0.003  # 元動画の音(440Hz)が入る/入らない

    # 2倍速: 音声の長さが半分になり、項目の終わり(2.0秒)より前に終わる。等速は項目の終わりまで続く
    voice_len = len(wave.open(str(assets["voice"])).readframes(10**9)) / (2 * wave.open(str(assets["voice"])).getframerate())
    assert voice_len > 1.0  # この確認の前提: 音声は1秒より長い
    fast = RenderSpec(**common, include_original_audio=False, audio=[AudioClip(str(assets["voice"]), 1000, 3000, 1.0, 2.0)])
    slow = RenderSpec(**common, include_original_audio=False, audio=[AudioClip(str(assets["voice"]), 1000, 3000, 1.0, 1.0)])
    t_end = 1.0 + voice_len / 2
    f_tail = _rms_windows(_render(fast, d), d, [(t_end + 0.15, t_end + 0.5)])[0]
    s_tail = _rms_windows(_render(slow, d), d, [(t_end + 0.15, t_end + 0.5)])[0]
    assert f_tail < 0.003 and s_tail > 0.02


@pytestmark_e2e
def test_render_without_source_video_uses_black_background_and_silent_track(assets):
    spec = RenderSpec(
        width=640, height=360, fps=15, total_ms=2000, font_path=FONT,
        subtitles=[SubtitleLayer(0, 2000, 0.5, 0.5, 60, "背景だけ")],
    )
    out = _render(spec, assets["dir"])
    info = _probe(out)
    assert any(s["codec_type"] == "audio" for s in info["streams"])  # 音声トラックは常にある
    assert abs(float(info["format"]["duration"]) - 2.0) < 0.15
    assert _close(_frame(out, 0.5, assets["dir"]).getpixel((5, 5)), (0, 0, 0), 8)


@pytestmark_e2e
def test_render_longer_than_source_video_holds_the_last_frame(assets):
    spec = RenderSpec(
        width=320, height=180, fps=15, total_ms=4500, video_path=str(assets["video"]), video_duration_ms=3000,
        video_has_audio=True, font_path=FONT, subtitles=[SubtitleLayer(3500, 4500, 0.5, 0.5, 40, "動画のあと")],
    )
    out = _render(spec, assets["dir"])
    assert abs(float(_probe(out)["format"]["duration"]) - 4.5) < 0.2
    assert _close(_frame(out, 4.0, assets["dir"]).getpixel((5, 5)), BG)  # 動画が終わっても、最後の画面が続く


@pytestmark_e2e
def test_render_handles_missing_image_and_simultaneous_subtitles(assets):
    d = assets["dir"]
    spec = RenderSpec(
        width=640, height=360, fps=15, total_ms=2000, font_path=FONT,
        characters=[CharacterLayer(0, 2000, 0.3, 0.6, 1.0, None, "魔理沙"),  # 画像なし → 仮の枠
                    CharacterLayer(0, 2000, 0.7, 0.6, 1.0, str(d / "not_an_image.png"), "霊夢")],  # 読めない画像 → 仮の枠
        subtitles=[SubtitleLayer(0, 2000, 0.5, 0.9, 40, "上の字幕"), SubtitleLayer(0, 2000, 0.5, 0.9, 40, "下の字幕")],
    )
    (d / "not_an_image.png").write_bytes(b"broken")
    out = _render(spec, d)
    img = _frame(out, 1.0, d)
    # 同時の字幕は重ならない: 基準位置(下)と、その1.4行上の両方に白い文字がある
    def white(box):
        return _white(img.crop(box))
    base_y, px = 360 * 0.9, 40 * 360 / 1080
    assert white((160, int(base_y - px * 0.7), 480, int(base_y + px * 0.7))) > 20
    assert white((160, int(base_y - px * 1.4 - px * 0.7), 480, int(base_y - px * 1.4 + px * 0.7))) > 20


@pytestmark_e2e
def test_render_errors_are_readable(assets):
    spec = RenderSpec(width=320, height=180, fps=15, total_ms=0, font_path=FONT)
    with pytest.raises(RenderError, match="長さが0"):
        render_to_file(spec, assets["dir"] / "w0", assets["dir"] / "x.mp4")
    bad_font = RenderSpec(width=320, height=180, fps=15, total_ms=1000, font_path="/no/such/font.ttf",
                          subtitles=[SubtitleLayer(0, 1000, 0.5, 0.9, 40, "x")])
    with pytest.raises(RenderError, match="フォント"):
        render_to_file(bad_font, assets["dir"] / "w1", assets["dir"] / "y.mp4")
    broken_audio = assets["dir"] / "broken.wav"
    broken_audio.write_bytes(b"not audio")
    spec = RenderSpec(width=320, height=180, fps=15, total_ms=1000, font_path=FONT,
                      audio=[AudioClip(str(broken_audio), 0, 500, 1.0, 1.0)])
    with pytest.raises(RenderError, match="FFmpeg"):
        render_to_file(spec, assets["dir"] / "w2", assets["dir"] / "z.mp4")
    with pytest.raises(RenderError, match="見つかりません"):
        render_to_file(_spec(total_ms=1000, font_path=FONT), assets["dir"] / "w3", assets["dir"] / "q.mp4", ffmpeg="no-such-ffmpeg-binary")


def test_probe_detects_audio_stream_and_actual_file(assets):
    from app.services.video_probe import parse_has_audio, probe_has_audio

    assert parse_has_audio({"streams": [{"codec_type": "video"}, {"codec_type": "audio"}]}) is True
    assert parse_has_audio({"streams": [{"codec_type": "video"}]}) is False and parse_has_audio({}) is False
    assert probe_has_audio(assets["video"]) is True
    silent = assets["dir"] / "silent.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=black:s=64x64:d=1", "-pix_fmt", "yuv420p", str(silent))
    assert probe_has_audio(silent) is False
    assert probe_has_audio(assets["dir"] / "missing.mp4") is False
    assert probe_has_audio(assets["video"], ffprobe="no-such-ffprobe") is False


@pytestmark_e2e
@pytest.mark.skipif(shutil.which("sh") is None, reason="sh が必要")
def test_render_falls_back_to_new_style_filter_option_for_newer_ffmpeg(assets, tmp_path):
    """FFmpeg 8 以降は -filter_complex_script が無く -/filter_complex になる。その場合に切り替わること。

    本物の新しい FFmpeg ではなく、「古い方の指定を拒否し、新しい指定を古い指定に読み替える」身代わりスクリプトで、
    切り替えの流れだけを確かめる(新しい FFmpeg 自体での動作は別途、実機で確認が必要)。
    """
    real = shutil.which("ffmpeg")
    fake = tmp_path / "fake_ffmpeg.sh"
    fake.write_text(
        '#!/bin/sh\n'
        'for a in "$@"; do\n'
        '  if [ "$a" = "-filter_complex_script" ]; then\n'
        '    echo "Unrecognized option \'filter_complex_script\'." >&2; exit 1\n'
        '  fi\n'
        'done\n'
        'args=""\n'
        f'exec {real} $(printf "%s\\n" "$@" | sed "s#^-/filter_complex\\$#-filter_complex_script#")\n'
    )
    fake.chmod(0o755)
    spec = RenderSpec(width=320, height=180, fps=15, total_ms=1000, font_path=FONT,
                      subtitles=[SubtitleLayer(0, 1000, 0.5, 0.5, 40, "確認")])
    out = tmp_path / "out.mp4"
    render_to_file(spec, tmp_path / "work", out, ffmpeg=str(fake))
    assert out.exists() and out.stat().st_size > 0
