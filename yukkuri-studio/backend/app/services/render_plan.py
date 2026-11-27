"""MP4書き出しの計画(純粋な関数と、データの入れ物)。Pillow・FFmpegに依存しないので、単体で確認できる。

見た目の規則は、編集画面のプレビュー(frontend の features/editor)と同じにする:
  - 立ち絵の高さ = 画面の高さ × 0.6 × 拡大率、位置は項目の中心(画面に対する割合)
  - 字幕の文字サイズ = 項目の値(既定40) × 画面の高さ ÷ 1080
  - 位置がほぼ同じ字幕が同時に出るときは、上へ 1.4 行ぶんずつずらす
"""
from dataclasses import dataclass, field

BASE_FONT_PX = 40  # 1080px高さのときの既定の字幕サイズ
CHARACTER_HEIGHT_RATIO = 0.6  # 拡大率1のときの立ち絵の高さ(画面の高さに対する割合)
DEFAULT_SIZE = (1920, 1080)
AUDIO_RATE = 48000
SUPPORTED_HEIGHTS = (480, 720, 1080)


@dataclass(frozen=True)
class CharacterLayer:
    start_ms: int
    end_ms: int
    x: float
    y: float
    scale: float
    image_path: str | None  # None = 画像が無い/読めない(仮の枠で表示)
    label: str  # 画像が無いときに枠に書く名前


@dataclass(frozen=True)
class SubtitleLayer:
    start_ms: int
    end_ms: int
    x: float
    y: float
    font_size: int | None
    text: str


@dataclass(frozen=True)
class AudioClip:
    path: str
    start_ms: int
    end_ms: int
    volume: float
    speed: float


@dataclass
class RenderSpec:
    width: int
    height: int
    fps: float
    total_ms: int
    video_path: str | None = None
    video_duration_ms: int | None = None
    video_has_audio: bool = False
    include_original_audio: bool = True
    original_volume: float = 1.0
    characters: list[CharacterLayer] = field(default_factory=list)  # 手前に重ねる順(セリフの順)
    subtitles: list[SubtitleLayer] = field(default_factory=list)
    audio: list[AudioClip] = field(default_factory=list)
    font_path: str | None = None


def _even(n: float) -> int:
    return max(2, int(round(n / 2)) * 2)  # H.264(yuv420p)は幅・高さが偶数である必要がある


def output_size(src_w: int | None, src_h: int | None, target_h: int | None) -> tuple[int, int]:
    """出力の大きさ。元動画があればその縦横比を保つ。target_h が無ければ元動画と同じ(元動画も無ければ1080p)。"""
    if not src_w or not src_h:
        h = target_h or DEFAULT_SIZE[1]
        return _even(h * 16 / 9), _even(h)
    h = target_h or src_h
    return _even(src_w * h / src_h), _even(h)


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int
    active: tuple[int, ...]  # この区間に表示されるレイヤーの番号(入力の順)


def build_segments(ranges: list[tuple[int, int]], total_ms: int) -> list[Segment]:
    """表示の組み合わせが変わる時刻で全体を区切る。何も出ない区間も含め、0〜total_ms を隙間なく返す。
    隣り合う区間で表示が同じなら1つにまとめる。"""
    marks = {0, total_ms}
    for s, e in ranges:
        marks.update(m for m in (s, e) if 0 < m < total_ms)
    points = sorted(marks)
    segments: list[Segment] = []
    for a, b in zip(points, points[1:]):
        active = tuple(i for i, (s, e) in enumerate(ranges) if s <= a and b <= e)
        if segments and segments[-1].active == active:
            segments[-1] = Segment(segments[-1].start_ms, b, active)
        else:
            segments.append(Segment(a, b, active))
    return segments


def subtitle_levels(positions: list[tuple[float, float]]) -> list[int]:
    """同時に出る字幕の段(0=基準位置、1以上=上へずらす)。位置がほぼ同じ(±0.05)字幕だけを重なりとみなす。"""
    placed: list[tuple[float, float, int]] = []
    levels: list[int] = []
    for x, y in positions:
        used = {lv for px, py, lv in placed if abs(px - x) < 0.05 and abs(py - y) < 0.05}
        level = 0
        while level in used:
            level += 1
        placed.append((x, y, level))
        levels.append(level)
    return levels


def pick_image(images: dict[str, str], expression: str | None, emotion: str, neutral: str = "neutral") -> str | None:
    """立ち絵に使う画像のキー。指定の表情 → セリフの感情 → 平常 → 何かある画像、の順に探す。"""
    for key in (expression, emotion, neutral):
        if key and key in images:
            return images[key]
    return next(iter(images.values()), None)


def _fmt(v: float) -> str:
    return f"{v:.3f}".rstrip("0").rstrip(".") or "0"


def video_filter(spec: RenderSpec) -> str:
    """元動画(または黒い背景)を出力サイズに整え、立ち絵・字幕の重ね映像(入力1)を載せる。"""
    w, h = spec.width, spec.height
    chain = [
        f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        f"fps={_fmt(spec.fps)}",
    ]
    pad_s = (spec.total_ms - (spec.video_duration_ms or 0)) / 1000 if spec.video_path else 0
    if pad_s > 0.01:  # 元動画より字幕・音声のほうが長いときは、最後の画面を保つ
        chain.append(f"tpad=stop_mode=clone:stop_duration={_fmt(pad_s)}")
    return (
        "[0:v]" + ",".join(chain) + "[base];\n"
        "[1:v]format=rgba[ov];\n"
        "[base][ov]overlay=format=auto:eof_action=pass[v]"
    )


def audio_filter(spec: RenderSpec, audio_names: list[str]) -> str:
    """セリフの音声(開始位置・速度・音量を反映)と元動画の音を混ぜる。
    ファイルは amovie で読む(入力が数百あっても、コマンドラインの長さ制限に掛からない)。名前は作業フォルダ内の短い名前。"""
    stereo = f"aresample={AUDIO_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo"
    total_s = _fmt(spec.total_ms / 1000)
    lines = [f"anullsrc=r={AUDIO_RATE}:cl=stereo,atrim=duration={total_s},asetpts=PTS-STARTPTS[a_base]"]
    labels = ["[a_base]"]
    if spec.video_path and spec.video_has_audio and spec.include_original_audio:
        lines.append(f"[0:a]{stereo},volume={_fmt(spec.original_volume)}[a_orig]")
        labels.append("[a_orig]")
    for i, (clip, name) in enumerate(zip(spec.audio, audio_names)):
        parts = [f"amovie={name}", stereo]
        if abs(clip.speed - 1.0) > 1e-6:
            parts.append(f"atempo={_fmt(clip.speed)}")  # 0.5〜2.0の範囲(編集画面の制限と同じ)
        parts += [
            f"atrim=duration={_fmt((clip.end_ms - clip.start_ms) / 1000)}",  # 項目の終わりで切る(プレビューと同じ)
            "asetpts=PTS-STARTPTS",
            f"volume={_fmt(clip.volume)}",
            f"adelay={clip.start_ms}:all=1",
        ]
        lines.append(",".join(parts) + f"[a{i}]")
        labels.append(f"[a{i}]")
    lines.append(
        "".join(labels)
        + f"amix=inputs={len(labels)}:normalize=0:dropout_transition=0:duration=first,alimiter=limit=0.95[a]"
    )
    return ";\n".join(lines)


def concat_list(entries: list[tuple[str, float]]) -> str:
    """concatデマルチプレクサ用の一覧。最後のファイルは、仕様上の癖により、もう一度書く必要がある。"""
    out = ["ffconcat version 1.0"]
    for name, seconds in entries:
        out += [f"file '{name}'", f"duration {seconds:.3f}"]
    if entries:
        out.append(f"file '{entries[-1][0]}'")
    return "\n".join(out) + "\n"


def parse_progress_line(line: str) -> int | None:
    """ffmpeg -progress の出力行から、書き出し済みの時間(ms)を取り出す。該当しない行は None。"""
    key, _, value = line.strip().partition("=")
    if key in ("out_time_us", "out_time_ms"):  # どちらもマイクロ秒(ffmpegの昔からの癖)
        try:
            return max(0, int(value)) // 1000
        except ValueError:
            return None
    return None
