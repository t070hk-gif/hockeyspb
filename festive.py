#!/usr/bin/env python3
"""
Новогодняя тема: с 15 декабря по 10 января баннеры «наряжаются» —
гирлянда сверху и снег. Посты праздничных дней получают наряженный баннер
(и он же — шапка баннера с результатами); турнирные таблицы — по
сегодняшней дате. После 10 января всё снова обычное, а у праздничных
постов остаётся праздничный вид.

    python3 festive.py         — нарядить все баннеры в banners_ny/ (для проверки)
"""
import math
import random
import re
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

BASE = Path(__file__).parent
NY_DIR = BASE / "banners_ny"
START, END = (12, 15), (1, 10)          # праздничный период (месяц, день), включительно
BULBS = [(255, 70, 70), (70, 220, 110), (255, 200, 50), (80, 170, 255), (255, 120, 220)]
SNOWFLAKE = ["1001001", "0101010", "0011100", "1111111", "0011100", "0101010", "1001001"]


def in_season(d=None):
    d = d or date.today()
    return (d.month, d.day) >= START or (d.month, d.day) <= END


def date_of(label):
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", label or "")
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def _dots(d, pattern, x, y, cell, color, dot=0.8):
    for r, row in enumerate(pattern):
        for c, bit in enumerate(row):
            if bit == "1":
                d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * dot, y + r * cell + cell * dot], fill=color)


def bulb_level(i, frame=None, frames=24):
    """Яркость лампочки i в кадре frame (0..1); frame=None — все горят."""
    if frame is None:
        return 1.0
    return 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2 * math.pi * frame / frames + i * 1.7))


def garland_layer(w, h, k=1.0, frame=None, frames=24, S=2):
    """Гирлянда во всю ширину w (k — масштаб относительно баннера 1200 px)."""
    glow = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    wire = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    wd = ImageDraw.Draw(wire)
    base_y, amp = 8 * k, 5 * k
    yy = lambda x: (base_y + amp * math.sin(x / (55.0 * k))) * S
    wd.line([(x * S, yy(x)) for x in range(0, w + 1, 6)], fill=(70, 80, 100, 255), width=max(2, int(2 * k)) * S)
    for i, x in enumerate(range(int(16 * k), w, int(40 * k))):
        y, col, lv = yy(x), BULBS[i % len(BULBS)], bulb_level(i, frame, frames)
        lit = tuple(int(30 + (v - 30) * lv) for v in col)
        gd.ellipse([x * S - 11 * k * S, y - 3 * k * S, x * S + 11 * k * S, y + 19 * k * S], fill=col + (int(200 * lv),))
        wd.ellipse([x * S - 5 * k * S, y + 2 * k * S, x * S + 5 * k * S, y + 15 * k * S], fill=lit + (255,))
    out = Image.alpha_composite(glow.filter(ImageFilter.GaussianBlur(8 * k * S)), wire)
    return out.resize((w, h), Image.LANCZOS)


def snow_layer(w, h, seed=7):
    S = 2
    rnd = random.Random(seed)
    snow = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(snow)
    for _ in range(int(w * h / 900)):
        x, y = rnd.randrange(w * S), rnd.randrange(h * S)
        r = rnd.choice((2, 3, 4)) * S // 2
        sd.ellipse([x, y, x + r, y + r], fill=(225, 238, 255, rnd.randrange(40, 120)))
    for fx, fy, cell in ((0.79, 0.62, 3), (0.80, 0.22, 2), (0.97, 0.84, 2), (0.70, 0.86, 2)):
        _dots(sd, SNOWFLAKE, int(fx * w * S), int(fy * h * S), cell * S, (215, 232, 255, 150))
    return snow.resize((w, h), Image.LANCZOS)


def falling_snow(w, h, frame, frames=48, seed=11, count=None, scale=1.0):
    """Падающий снег: каждая снежинка за круг пролетает целое число высот — ролик зациклен без рывка."""
    S = 2
    rnd = random.Random(seed)
    layer = Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for _ in range(count or int(w * h / 1400)):
        x0, y0 = rnd.uniform(0, w), rnd.uniform(0, h)
        laps = rnd.choice((1, 1, 2))                       # скорость: 1 или 2 высоты за круг
        size = rnd.choice((2, 3, 3, 4, 5)) * scale
        alpha = rnd.randrange(90, 210)
        sway, phase = rnd.uniform(2, 6) * scale, rnd.uniform(0, 2 * math.pi)
        t = frame / frames
        y = (y0 + laps * h * t) % h
        x = x0 + sway * math.sin(2 * math.pi * t * laps + phase)
        d.ellipse([x * S, y * S, (x + size) * S, (y + size) * S], fill=(232, 242, 255, alpha))
    return layer.resize((w, h), Image.LANCZOS)


def overlay(img, seed=7, frame=None, frames=24):
    """Снег и гирлянда поверх баннера (размер сохраняется). frame — кадр мигания."""
    w, h = img.size
    out = Image.alpha_composite(img.convert("RGBA"), snow_layer(w, h, seed))
    out = Image.alpha_composite(out, garland_layer(w, h, w / 1200, frame, frames))
    return out.convert("RGB")


def animate(still, out_mp4, top_h=None, snow_h=None, frames=48, fps=12):
    """Мигающая гирлянда и падающий снег поверх готовой картинки (баннер с результатами и т. п.).
    still — картинка БЕЗ гирлянды; гирлянда — в полосе top_h, снег падает в полосе snow_h (шапка)."""
    import imageio.v2 as imageio
    import numpy
    base = still.convert("RGBA")
    w, h = base.size
    top_h = top_h or int(40 * w / 1200)
    snow_h = snow_h or int(260 * w / 1200)
    w2, h2 = w - w % 2, h - h % 2
    with imageio.get_writer(out_mp4, fps=fps, codec="libx264", quality=8, macro_block_size=1,
                            pixelformat="yuv420p") as wr:
        for fr in range(frames):
            frame = base.copy()
            frame.alpha_composite(falling_snow(w, snow_h, fr, frames, scale=w / 1200), (0, 0))
            frame.alpha_composite(garland_layer(w, top_h, w / 1200, fr, frames), (0, 0))
            wr.append_data(numpy.asarray(frame.convert("RGB").crop((0, 0, w2, h2))))
    return out_mp4


def season_banner(path, date_label=None):
    """Наряженный баннер, если дата (поста или сегодня) — праздничная; иначе тот же path."""
    if path is None:
        return path
    path = Path(path)
    d = date_of(date_label) if date_label else None
    if not in_season(d or date.today()) or not path.exists():
        return path
    out = NY_DIR / path.name
    if not out.exists() or out.stat().st_mtime < path.stat().st_mtime:
        NY_DIR.mkdir(exist_ok=True)
        overlay(Image.open(path)).save(out)
    return out


def can_animate():
    """Можно ли собирать ролики (установлены imageio, imageio-ffmpeg, numpy)."""
    try:
        import imageio.v2  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


if __name__ == "__main__":
    NY_DIR.mkdir(exist_ok=True)
    n = 0
    for p in sorted((BASE / "banners").glob("*.png")):
        overlay(Image.open(p)).save(NY_DIR / p.name)
        n += 1
    print(f"Наряжено баннеров: {n} в {NY_DIR}")