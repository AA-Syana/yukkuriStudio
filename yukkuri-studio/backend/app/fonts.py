"""字幕・仮立ち絵の文字に使う日本語フォントを探す。見つからなければ None(呼び出し側で扱いを決める)。"""
from pathlib import Path

# 太めのフォントを先に。環境変数 RENDER_FONT_PATH で明示できる
_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/meiryob.ttc", "C:/Windows/Fonts/BIZ-UDGothicB.ttc",
    "C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/meiryo.ttc", "C:/Windows/Fonts/msgothic.ttc",
    # macOS
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    # Linux
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]


def find_font(explicit: str = "") -> str | None:
    for candidate in ([explicit] if explicit else []) + _CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    return None
