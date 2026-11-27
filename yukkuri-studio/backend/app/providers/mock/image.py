"""モック画像: 表情ごとに顔が変わるPNGの仮立ち絵を作る。seed(キャラクターID)から色を決めるので、
同じキャラクターは表情が変わっても同じ配色になる(外見の一貫性の見本)。

PNGにしているのは、ブラウザでの表示とMP4の書き出し(Pillow/FFmpeg)の両方でそのまま使えるため。
"""
import colorsys
import hashlib
import io

from PIL import Image, ImageDraw, ImageFont

from ...core.config import settings
from ...fonts import find_font
from ..base import ImageRequest, ImageResult

W, H = 300, 450
SS = 3  # 作画は3倍の大きさで行って縮小する(輪郭をなめらかにする)
INK = (51, 51, 51, 255)


def _hsl(h: int, s: int, l: int) -> tuple[int, int, int, int]:
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return (round(r * 255), round(g * 255), round(b * 255), 255)


def _quad(p0, c, p1, steps=16):
    """2次ベジェ曲線の点列。"""
    return [
        ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * c[0] + t**2 * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * c[1] + t**2 * p1[1])
        for t in (i / steps for i in range(steps + 1))
    ]


class MockImageProvider:
    name = "mock"

    def generate(self, req: ImageRequest) -> ImageResult:
        hue = int(hashlib.md5(req.seed.encode()).hexdigest()[:4], 16) % 360
        img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        k = SS

        def pt(x, y):  # 顔の中心(150,150)を原点とした座標 -> 画像の座標
            return ((150 + x) * k, (150 + y) * k)

        def line(points, width):
            d.line([pt(*p) for p in points], fill=INK, width=width * k, joint="curve")
            for p in (points[0], points[-1]):  # 線の端を丸める
                x, y = pt(*p)
                d.ellipse([x - width * k / 2, y - width * k / 2, x + width * k / 2, y + width * k / 2], fill=INK)

        def dot(x, y, r, fill=INK, outline=None, ow=0):
            cx, cy = pt(x, y)
            d.ellipse([cx - r * k, cy - r * k, cx + r * k, cy + r * k], fill=fill, outline=outline, width=ow * k)

        d.rounded_rectangle([60 * k, 250 * k, 240 * k, 440 * k], radius=50 * k, fill=_hsl(hue, 55, 55))
        d.ellipse([45 * k, 45 * k, 255 * k, 255 * k], fill=_hsl((hue + 20) % 360, 70, 85))

        e = req.expression
        if e == "happy":
            line(_quad((-52, -8), (-40, -26), (-28, -8)), 6)
            line(_quad((28, -8), (40, -26), (52, -8)), 6)
            mouth = _quad((-32, 32), (0, 70), (32, 32))
            d.polygon([pt(*p) for p in mouth], fill=(255, 255, 255, 255))
            line(mouth + [mouth[0]], 5)
        elif e == "angry":
            dot(-40, -6, 9); dot(40, -6, 9)
            line([(-58, -34), (-24, -20)], 7); line([(58, -34), (24, -20)], 7)
            line(_quad((-28, 58), (0, 36), (28, 58)), 6)
        elif e == "surprised":
            for x in (-40, 40):
                dot(x, -10, 15, fill=(255, 255, 255, 255), outline=INK, ow=4)
                dot(x, -10, 5)
            cx, cy = pt(0, 50)
            d.ellipse([cx - 13 * k, cy - 18 * k, cx + 13 * k, cy + 18 * k], fill=INK)
        elif e == "sad":
            dot(-40, -6, 9); dot(40, -6, 9)
            line([(-58, -22), (-24, -34)], 6); line([(58, -22), (24, -34)], 6)
            line(_quad((-26, 56), (0, 38), (26, 56)), 6)
        else:  # neutral
            dot(-40, -10, 9); dot(40, -10, 9)
            line([(-25, 45), (25, 45)], 6)

        img = img.resize((W, H), Image.LANCZOS)
        font_path = find_font(settings.render_font_path)
        if font_path and req.character_name:
            try:
                font = ImageFont.truetype(font_path, 26)
                ImageDraw.Draw(img).text((150, 400), req.character_name, fill=(255, 255, 255, 255), font=font, anchor="mm")
            except OSError:
                pass  # フォントが読めなくても、名前なしの仮画像は作る
        out = io.BytesIO()
        img.save(out, format="PNG")
        return ImageResult(data=out.getvalue(), ext=".png")
