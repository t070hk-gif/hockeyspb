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


def overlay(img, seed=7):
    """Гирлянда сверху и снег поверх баннера (размер сохраняется)."""
    S = 2
    w, h = img.size
    big = img.convert("RGBA").resize((w * S, h * S), Image.LANCZOS)
    rnd = random.Random(seed)
    snow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(snow)
    for _ in range(int(w * h / 900)):
        x, y = rnd.randrange(w * S), rnd.randrange(h * S)
        r = rnd.choice((2, 3, 4)) * S // 2
        sd.ellipse([x, y, x + r, y + r], fill=(225, 238, 255, rnd.randrange(40, 120)))
    for fx, fy, cell in ((0.79, 0.62, 3), (0.80, 0.22, 2), (0.97, 0.84, 2), (0.70, 0.86, 2)):
        _dots(sd, SNOWFLAKE, int(fx * w * S), int(fy * h * S), cell * S, (215, 232, 255, 150))
    glow = Image.new("RGBA", big.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    wire = Image.new("RGBA", big.size, (0, 0, 0, 0))
    wd = ImageDraw.Draw(wire)
    base_y, amp = 8, 5
    pts = [(x * S, int((base_y + amp * math.sin(x / 55.0)) * S)) for x in range(0, w + 1, 6)]
    wd.line(pts, fill=(70, 80, 100, 255), width=2 * S)
    for i, x in enumerate(range(16, w, 40)):
        y = int((base_y + amp * math.sin(x / 55.0)) * S)
        col = BULBS[i % len(BULBS)]
        gd.ellipse([x * S - 11 * S, y - 3 * S, x * S + 11 * S, y + 19 * S], fill=col + (190,))
        wd.ellipse([x * S - 5 * S, y + 2 * S, x * S + 5 * S, y + 15 * S], fill=col + (255,))
    out = Image.alpha_composite(big, snow)
    out = Image.alpha_composite(out, glow.filter(ImageFilter.GaussianBlur(8 * S)))
    out = Image.alpha_composite(out, wire)
    return out.resize((w, h), Image.LANCZOS).convert("RGB")


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


if __name__ == "__main__":
    NY_DIR.mkdir(exist_ok=True)
    n = 0
    for p in sorted((BASE / "banners").glob("*.png")):
        overlay(Image.open(p)).save(NY_DIR / p.name)
        n += 1
    print(f"Наряжено баннеров: {n} в {NY_DIR}")
