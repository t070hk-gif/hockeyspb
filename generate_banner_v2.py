#!/usr/bin/env python3
"""
Баннеры постов в новом стиле (по образцу баннеров Первенства Москвы / МО):
1200×310, тёмная зона слева с крупным годом и наклонённой плашкой турнира,
справа цветная диагональ со светлой полосой и эмблема федерации.

    python3 generate_banner_v2.py              — сгенерировать весь набор в banners_v2/
    python3 generate_banner_v2.py --install    — сгенерировать и заменить banners/
                                                 (старые баннеры сохраняются в banners_old/)
"""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
W, H = 1200, 260
K = H / 310          # масштаб по высоте относительно исходного макета 1200×310
BG = (16, 20, 30)                    # цвет тёмной зоны
SPLIT_TOP, SPLIT_BOTTOM = 0.52, 0.42  # где начинается цветная диагональ (доля ширины сверху и снизу)
OUTLINE = (10, 10, 15)
PLATE_TEXT = (10, 10, 20)
LOGO_PATH = BASE / "fhspb_logo.png"

GROUP_STYLE = {
    "A": ((233, 30, 85), (255, 105, 135), "GROUP A"),
    "B": ((0, 150, 210), (70, 210, 235), "GROUP B"),
    None: ((0, 150, 210), (70, 210, 235), None),
}
BADGES = {
    "ПЕРВЕНСТВО": ("ПЕРВЕНСТВО СПБ", (98, 70, 210), (255, 255, 255)),
    "КУБОК": ("КУБОК СПБ", (255, 193, 7), PLATE_TEXT),
    "КУБОК ФЕДЕРАЦИИ": ("КУБОК ФЕДЕРАЦИИ", (255, 193, 7), PLATE_TEXT),
    "КУБОК РОССИИ": ("КУБОК РОССИИ", (255, 193, 7), PLATE_TEXT),
}

FONT_CANDIDATES = [BASE / "fonts" / "DejaVuSans-Bold.ttf", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                   Path("/Library/Fonts/DejaVuSans-Bold.ttf"), BASE / "fonts" / "PT_Sans-Web-Bold.ttf"]


def font(size):
    for p in FONT_CANDIDATES:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def make_banner(year, group=None, tournament="ПЕРВЕНСТВО", out_path=None):
    main, light, group_label = GROUP_STYLE.get(group, GROUP_STYLE[None])
    badge_text, badge_fill, badge_text_color = BADGES[tournament]

    img = Image.new("RGBA", (W, H), BG + (255,))

    # тонкие диагональные линии в тёмной зоне
    deco = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(deco)
    for x in range(-200, 900, 34):
        dd.line([(x + round(120 * K), 0), (x, H)], fill=(255, 255, 255, 18), width=6)
    img = Image.alpha_composite(img, deco)
    d = ImageDraw.Draw(img)

    # цветная диагональ и светлая полоса вдоль неё
    top_x, bottom_x = int(W * SPLIT_TOP), int(W * SPLIT_BOTTOM)
    d.polygon([(top_x, 0), (W, 0), (W, H), (bottom_x, H)], fill=main)
    d.polygon([(top_x, 0), (top_x + 100, 0), (bottom_x + 100, H), (bottom_x, H)], fill=light)

    # плашка турнира с наклоном
    bf = font(round((30 if len(badge_text) <= 18 else 22) * K))
    tw = d.textlength(badge_text, font=bf)
    bw, bh = max(int(520 * K), int(tw + 60)), round(56 * K)
    badge = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle([0, 0, bw - 1, bh - 1], radius=10, fill=badge_fill)
    bd.text((bw / 2, bh / 2), badge_text, font=bf, fill=badge_text_color, anchor="mm")
    badge = badge.rotate(3, expand=True, resample=Image.BICUBIC)
    badge_y, year_y = round(26 * K) - 10, round(78 * K)
    year_font = font(round(130 * K))
    if not group_label:
        # Без плашки группы (кубки): блок «турнир + год» — по центру высоты
        year_bottom = year_y + d.textbbox((0, 0), str(year), font=year_font, stroke_width=4)[3]
        shift = (H - (year_bottom - badge_y)) // 2 - badge_y
        badge_y, year_y = badge_y + shift, year_y + shift
    img.alpha_composite(badge, (40, badge_y))

    # год с обводкой
    d = ImageDraw.Draw(img)
    d.text((52, year_y), str(year), font=year_font, fill=(255, 255, 255),
           stroke_width=4, stroke_fill=OUTLINE)

    # плашка группы
    if group_label:
        gf = font(round(34 * K))
        gw = d.textlength(group_label, font=gf)
        x0, y0 = 60, round(210 * K)
        ph = round((34 + 28) * K)
        d.rounded_rectangle([x0, y0, x0 + gw + 44, y0 + ph], radius=8, fill=light)
        d.text((x0 + 22, y0 + ph / 2), group_label, font=gf, fill=PLATE_TEXT, anchor="lm")

    # эмблема справа
    size = round(190 * K)
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
        logo.thumbnail((size, size), Image.LANCZOS)
    except Exception:
        logo = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ld = ImageDraw.Draw(logo)
        ld.ellipse([0, 0, size - 1, size - 1], fill=(255, 255, 255), outline=(10, 40, 120), width=8)
        ld.text((size / 2, size / 2), "ФХ СПб", font=font(round(34 * K)), fill=(10, 40, 120), anchor="mm")
    img.alpha_composite(logo, (W - 40 - logo.width, (H - logo.height) // 2))

    img = img.convert("RGB")
    if out_path:
        img.save(out_path)
    return img


# Тот же набор и те же имена файлов, что у нынешних баннеров (banners/)
SET = (
    [(y, None, "КУБОК", f"{y}_cup.png") for y in ("2010", "2011", "2012", "2013", "2014", "2015")]
    + [(y, None, "КУБОК ФЕДЕРАЦИИ", f"{y}_cup.png") for y in ("2016", "2017", "2018")]
    + [("2009", None, "ПЕРВЕНСТВО", "2009_champ.png"), ("2010", None, "ПЕРВЕНСТВО", "2010_champ.png")]
    + [(y, g, "ПЕРВЕНСТВО", f"{y}_group{g.lower()}_champ.png")
       for y in ("2011", "2012", "2013", "2014", "2015") for g in ("A", "B")]
    + [("2011", None, "КУБОК РОССИИ", "2011_kubokrossii.png")]
)


def main():
    out_dir = BASE / "banners_v2"
    out_dir.mkdir(exist_ok=True)
    for year, group, tournament, name in SET:
        make_banner(year, group, tournament, out_dir / name)
    print(f"Сгенерировано {len(SET)} баннеров в {out_dir}")
    if "--install" in sys.argv:
        live, backup = BASE / "banners", BASE / "banners_old"
        if live.exists() and not backup.exists():
            shutil.copytree(live, backup)
            print(f"Старые баннеры сохранены в {backup}")
        live.mkdir(exist_ok=True)
        for _, _, _, name in SET:
            shutil.copy(out_dir / name, live / name)
        print(f"Новые баннеры установлены в {live}")


if __name__ == "__main__":
    main()
