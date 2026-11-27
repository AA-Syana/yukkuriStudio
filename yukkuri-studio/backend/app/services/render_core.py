"""MP4書き出しの実処理(DBに依存しない)。RenderSpec を受け取り、1つのMP4ファイルを作る。

流れ:
  1. 表示の組み合わせが変わる時刻で区切り、区間ごとに「立ち絵+字幕」を1枚の透明PNGに合成する(Pillow)。
  2. それらを1本の重ね映像(concat)として、元動画(または黒い背景)の上に重ねる(FFmpeg)。
  3. セリフの音声を、開始位置・速度・音量を反映して混ぜ、元動画の音も加える(FFmpeg)。
立ち絵・字幕を1本の映像にまとめるので、セリフが数百あってもFFmpegのコマンドは大きくならない。
"""
import shutil
import subprocess
from collections import deque
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .render_plan import (
    BASE_FONT_PX, CHARACTER_HEIGHT_RATIO, RenderSpec, Segment, audio_filter, build_segments, concat_list,
    parse_progress_line, subtitle_levels, video_filter,
)

COMPOSE_SHARE = 15  # 進捗(%)のうち、画像の合成に割り当てる分。残りはFFmpegの変換


class RenderError(Exception):
    """利用者に見せてよいメッセージを持つ書き出しの失敗。"""


# ---------------- 画像の合成 ----------------
def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """文字数ベースで折り返す(日本語は単語の区切りが無いため)。改行は尊重する。"""
    lines: list[str] = []
    for raw in text.split("\n"):
        current = ""
        for ch in raw:
            if current and font.getlength(current + ch) > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
        lines.append(current)
    return lines


def _paste(canvas: Image.Image, layer: Image.Image, cx: float, cy: float) -> None:
    """layer の中心を (cx, cy) に置く。画面の外にはみ出す部分は切り取る。"""
    x, y = round(cx - layer.width / 2), round(cy - layer.height / 2)
    sx, sy = max(0, -x), max(0, -y)
    dx, dy = max(0, x), max(0, y)
    w, h = min(layer.width - sx, canvas.width - dx), min(layer.height - sy, canvas.height - dy)
    if w > 0 and h > 0:
        canvas.alpha_composite(layer, dest=(dx, dy), source=(sx, sy, sx + w, sy + h))


class FrameComposer:
    """区間ごとの合成画像を作る。読み込んだ立ち絵は使い回す。"""

    def __init__(self, spec: RenderSpec):
        self.spec = spec
        self._images: dict[str, Image.Image | None] = {}
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def _font(self, px: int) -> ImageFont.FreeTypeFont:
        if px not in self._fonts:
            try:
                self._fonts[px] = ImageFont.truetype(self.spec.font_path, px)  # type: ignore[arg-type]
            except (OSError, TypeError):
                raise RenderError("字幕用の日本語フォントを読み込めません。環境変数 RENDER_FONT_PATH にフォントのパスを指定してください")
        return self._fonts[px]

    def _image(self, path: str) -> Image.Image | None:
        if path not in self._images:
            try:
                with Image.open(path) as im:
                    self._images[path] = im.convert("RGBA")
            except Exception:
                self._images[path] = None  # 読めない画像は、仮の枠で表示する
        return self._images[path]

    def _character(self, canvas: Image.Image, layer) -> None:
        w, h = canvas.size
        target_h = max(2, round(h * CHARACTER_HEIGHT_RATIO * layer.scale))
        src = self._image(layer.image_path) if layer.image_path else None
        if src is not None:
            sprite = src.resize((max(1, round(src.width * target_h / src.height)), target_h), Image.LANCZOS)
        else:  # 仮の枠(プレビューと同じ。縦横比3:5)
            sprite = Image.new("RGBA", (max(2, round(target_h * 0.6)), target_h), (255, 255, 255, 46))
            d = ImageDraw.Draw(sprite)
            d.rectangle([0, 0, sprite.width - 1, sprite.height - 1], outline=(170, 170, 187, 255), width=max(1, target_h // 200))
            if self.spec.font_path:
                font = self._font(max(10, round(h / 40)))
                d.text((sprite.width / 2, sprite.height / 2), f"{layer.label}\n（画像なし）", fill=(255, 255, 255, 255),
                       font=font, anchor="mm", align="center")
        _paste(canvas, sprite, layer.x * w, layer.y * h)

    def _subtitle(self, canvas: Image.Image, layer, level: int) -> None:
        w, h = canvas.size
        px = max(8, round((layer.font_size or BASE_FONT_PX) * h / 1080))
        font = self._font(px)
        lines = _wrap(layer.text, font, w * 0.9)
        line_h = px * 1.3
        block_h = line_h * len(lines)
        cx = layer.x * w
        top = layer.y * h - block_h / 2 - level * 1.4 * px  # 同時の字幕は上へずらして重ねない
        d = ImageDraw.Draw(canvas)
        stroke = max(1, round(px / 10))
        for i, line in enumerate(lines):
            d.text((cx, top + line_h * i + line_h / 2), line, fill=(255, 255, 255, 255), font=font, anchor="mm",
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 255))

    def compose(self, active_chars: list[int], active_subs: list[int]) -> Image.Image:
        canvas = Image.new("RGBA", (self.spec.width, self.spec.height), (0, 0, 0, 0))
        for i in active_chars:
            self._character(canvas, self.spec.characters[i])
        levels = subtitle_levels([(self.spec.subtitles[i].x, self.spec.subtitles[i].y) for i in active_subs])
        for i, level in zip(active_subs, levels):
            self._subtitle(canvas, self.spec.subtitles[i], level)
        return canvas


def compose_segments(spec: RenderSpec, workdir: Path, on_progress: Callable[[int], None]) -> list[tuple[str, float]]:
    """重ね映像の素材を作る。戻り値は [(PNGのファイル名, 表示する秒数)]。"""
    n_char = len(spec.characters)
    ranges = [(c.start_ms, c.end_ms) for c in spec.characters] + [(s.start_ms, s.end_ms) for s in spec.subtitles]
    segments: list[Segment] = build_segments(ranges, spec.total_ms)
    composer = FrameComposer(spec)
    files: dict[tuple[int, ...], str] = {}  # 同じ表示の組み合わせは、同じ画像を使い回す
    entries: list[tuple[str, float]] = []
    for n, seg in enumerate(segments):
        if seg.active not in files:
            name = f"ov{len(files)}.png"
            chars = [i for i in seg.active if i < n_char]
            subs = [i - n_char for i in seg.active if i >= n_char]
            composer.compose(chars, subs).save(workdir / name, format="PNG", compress_level=1)
            files[seg.active] = name
        entries.append((files[seg.active], (seg.end_ms - seg.start_ms) / 1000))
        on_progress(round((n + 1) * COMPOSE_SHARE / len(segments)))
    return entries


# ---------------- FFmpeg ----------------
def _run_ffmpeg(cmd: list[str], cwd: Path, total_ms: int, on_progress: Callable[[int], None]) -> None:
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        raise RenderError("FFmpeg が見つかりません。FFmpeg をインストールして PATH に追加するか、環境変数 FFMPEG_PATH を設定してください")
    tail: deque[str] = deque(maxlen=12)  # 失敗時に見せる、最後のエラー出力
    assert proc.stdout is not None
    last = -1
    for line in proc.stdout:
        ms = parse_progress_line(line)
        if ms is not None:
            pct = COMPOSE_SHARE + min(99 - COMPOSE_SHARE, round(ms * (99 - COMPOSE_SHARE) / max(total_ms, 1)))
            if pct != last:
                last = pct
                on_progress(pct)
        elif "=" not in line or " " in line.split("=", 1)[0]:  # progress の key=value 行以外はエラー出力
            if line.strip():
                tail.append(line.strip())
    if proc.wait() != 0:
        raise RenderError("FFmpegでの書き出しに失敗しました: " + " / ".join(tail)[-400:])


def render_to_file(
    spec: RenderSpec, workdir: Path, output: Path, ffmpeg: str = "ffmpeg",
    on_progress: Callable[[int], None] = lambda pct: None,
) -> None:
    """spec どおりのMP4を output に書き出す。workdir は作業用の空きフォルダ(呼び出し側が後で消す)。"""
    workdir.mkdir(parents=True, exist_ok=True)
    if spec.total_ms <= 0:
        raise RenderError("書き出す内容がありません(長さが0です)")

    entries = compose_segments(spec, workdir, on_progress)
    (workdir / "overlay.txt").write_text(concat_list(entries), encoding="utf-8")

    audio_names: list[str] = []
    for i, clip in enumerate(spec.audio):
        name = f"a{i}{Path(clip.path).suffix.lower()}"
        shutil.copyfile(clip.path, workdir / name)  # amovie に短い相対パスで渡すため
        audio_names.append(name)
    graph = video_filter(spec) + ";\n" + audio_filter(spec, audio_names)
    (workdir / "graph.txt").write_text(graph, encoding="utf-8")

    total_s = f"{spec.total_ms / 1000:.3f}"
    if spec.video_path:
        source = ["-i", str(Path(spec.video_path).resolve())]
    else:
        source = ["-f", "lavfi", "-i", f"color=c=black:s={spec.width}x{spec.height}:r={spec.fps:g}:d={total_s}"]
    def command(graph_option: str) -> list[str]:
        return [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
            *source, "-f", "concat", "-safe", "0", "-i", "overlay.txt",
            graph_option, "graph.txt", "-map", "[v]", "-map", "[a]",
            "-t", total_s,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
            str(output.resolve()),
        ]

    # フィルタ定義ファイルの指定方法は FFmpeg のバージョンで違う(古い: -filter_complex_script / 新しい: -/filter_complex)
    try:
        _run_ffmpeg(command("-filter_complex_script"), workdir, spec.total_ms, on_progress)
    except RenderError as e:
        if "Unrecognized option" not in str(e):
            raise
        _run_ffmpeg(command("-/filter_complex"), workdir, spec.total_ms, on_progress)
    if not output.exists() or output.stat().st_size == 0:
        raise RenderError("書き出したファイルが作成されませんでした")
    on_progress(100)
