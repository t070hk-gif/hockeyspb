#!/usr/bin/env python3
"""
Баннеры турниров в стиле «Табло»: тёмный корпус табло арены, год светится
жёлтыми точками, буква группы — цветом группы, плашка турнира, эмблема
федерации справа. 1200×260, те же имена файлов, что у прежних баннеров.

    python3 generate_banner_v3.py              — сгенерировать набор в banners_tablo/
    python3 generate_banner_v3.py --install    — сгенерировать и заменить banners/
                                                 (прежние сохраняются в banners_before_tablo/)
    python3 generate_banner_v3.py --fetch-kr-logo   — скачать логотип Кубка России со страницы турнира
    python3 generate_banner_v3.py --friendly   — баннеры товарищеских игр в banners_friendly/
                                                 (прежние — в banners_friendly_before_tablo/)
"""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
W, H = 1200, 260
FONT_BOLD = BASE / "fonts" / "PT_Sans-Web-Bold.ttf"
LOGO_PATH = BASE / "fhspb_logo.png"

BG, HOUSING, HOUSING_EDGE = (9, 12, 20), (20, 24, 34), (52, 60, 78)
LED_ON, LED_OFF, LED_GLOW = (255, 196, 40), (26, 23, 18), (255, 170, 0, 255)
GROUP_COLOR = {"A": (233, 30, 85), "B": (0, 150, 210), None: (0, 150, 210)}
GROUP_LED = {"A": (255, 105, 135), "B": (70, 210, 235)}
CUP_AMBER = (255, 176, 0)
PLATES = {
    "ПЕРВЕНСТВО": "ПЕРВЕНСТВО СПБ",
    "КУБОК": "КУБОК СПБ",
    "КУБОК ФЕДЕРАЦИИ": "КУБОК ФЕДЕРАЦИИ",
    "КУБОК РОССИИ": "КУБОК РОССИИ",
    "ТОВАРИЩЕСКИЙ": "ТОВАРИЩЕСКИЙ МАТЧ",
    "ТЕРРИТОРИЯ ХОККЕЯ U15": "ТЕРРИТОРИЯ ХОККЕЯ U15",
    "ТЕРРИТОРИЯ ХОККЕЯ U14": "ТЕРРИТОРИЯ ХОККЕЯ U14",
}
TERRITORIYA_TEAL = (0, 150, 136)              # «Территория хоккея» — бирюзовая плашка
FRIENDLY_GREEN = (40, 170, 90)
ROSSII_BLUE = (0, 57, 166)                    # Кубок России — синяя плашка с триколором
KR_LOGO_PATH = BASE / "kubok_rossii_logo.png" # логотип Кубка России (python3 generate_banner_v3.py --fetch-kr-logo)

# Точечный шрифт 5×7, как на табло
GLYPHS = {
    "0": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00110", "01000", "10000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "А": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "Б": ["11111", "10000", "10000", "11110", "10001", "10001", "11110"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
}


def font(size):
    try:
        return ImageFont.truetype(str(FONT_BOLD), size)
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)


def led(draw, text, x, y, cell, on, off=None, dot=0.8):
    """Рисует текст точками; off=None — погашенные точки не рисуются."""
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit != "1" and off is None:
                    continue
                cx, cy = x + c * cell, y + r * cell
                draw.ellipse([cx, cy, cx + cell * dot, cy + cell * dot], fill=on if bit == "1" else off)
        x += cell * (6.2 if ch != ":" else 4.4)
    return x


def make_banner(year, group=None, tournament="ПЕРВЕНСТВО", out_path=None):
    img = Image.new("RGBA", (W, H), BG + (255,))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([20, 18, 900, H - 18], radius=18, fill=HOUSING, outline=HOUSING_EDGE, width=3)

    label = PLATES[tournament]
    plate = (GROUP_COLOR[group] if tournament == "ПЕРВЕНСТВО" else
             FRIENDLY_GREEN if tournament == "ТОВАРИЩЕСКИЙ" else
             ROSSII_BLUE if tournament == "КУБОК РОССИИ" else
             TERRITORIYA_TEAL if tournament.startswith("ТЕРРИТОРИЯ") else CUP_AMBER)
    ink = (255, 255, 255) if (tournament in ("ПЕРВЕНСТВО", "ТОВАРИЩЕСКИЙ", "КУБОК РОССИИ")
                              or tournament.startswith("ТЕРРИТОРИЯ")) else (20, 20, 20)
    pf = font(26)
    pw = d.textlength(label, font=pf) + 36
    d.rounded_rectangle([44, 34, 44 + pw, 76], radius=8, fill=plate)
    d.text((62, 55), label, font=pf, fill=ink, anchor="lm")
    if tournament == "КУБОК РОССИИ":                  # триколор под плашкой
        third = pw / 3
        for i, col in enumerate(((255, 255, 255), (0, 57, 166), (213, 43, 30))):
            d.rectangle([44 + i * third, 80, 44 + (i + 1) * third, 85], fill=col)
        d.rectangle([44, 80, 44 + pw, 85], outline=(70, 80, 100), width=1)

    cell = 18
    if not year:                                      # год неизвестен — прочерки на табло
        end = led(d, "----", 54, 98, cell, (130, 100, 40), LED_OFF)
    else:
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        led(ImageDraw.Draw(glow), str(year), 54, 98, cell, LED_GLOW)
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(7)))
        d = ImageDraw.Draw(img)
        end = led(d, str(year), 54, 98, cell, LED_ON, LED_OFF)
    if group in ("A", "B"):
        letter = "А" if group == "A" else "Б"
        d.text((end + 44, 104), "ГРУППА", font=font(22), fill=(150, 160, 180))
        led(d, letter, end + 44, 136, 12, GROUP_LED[group], (24, 26, 32))

    size, cx, cy = 150, 1052, H // 2
    if tournament == "КУБОК РОССИИ" and KR_LOGO_PATH.exists():
        # Логотип Кубка России — без круга, крупнее, без собственного фона
        logo = _logo_without_background(Image.open(KR_LOGO_PATH))
        box = 200
        k = min(box / logo.width, box / logo.height)
        logo = logo.resize((max(1, round(logo.width * k)), max(1, round(logo.height * k))), Image.LANCZOS)
        img.alpha_composite(logo, (cx - logo.width // 2, cy - logo.height // 2))
        return _finish(img, out_path)
    logo_path = LOGO_PATH
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize((size, size), Image.LANCZOS)
        d.ellipse([cx - size // 2 - 8, cy - size // 2 - 8, cx + size // 2 + 8, cy + size // 2 + 8], fill=(255, 255, 255))
        img.alpha_composite(logo, (cx - size // 2, cy - size // 2))
    except Exception:
        d.ellipse([cx - 75, cy - 75, cx + 75, cy + 75], fill=(255, 255, 255))
        d.text((cx, cy), "ФХ СПб", font=font(28), fill=(10, 40, 120), anchor="mm")

    return _finish(img, out_path)


def _finish(img, out_path):
    img = img.convert("RGB")
    if out_path:
        img.save(out_path)
    return img


def _logo_without_background(src, tol=48):
    """Логотип без фона: если картинка непрозрачная — цвет фона берётся по углам и становится
    прозрачным; пустые поля обрезаются, чтобы логотип был крупным."""
    img = src.convert("RGBA")
    w, h = img.size
    corners = [img.getpixel((x, y)) for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1))]
    if all(a > 200 for *_, a in corners):
        bg = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
        px = img.load()
        for y in range(h):
            for x in range(w):
                r, g, b, a = px[x, y]
                dist = abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])
                if dist < tol:
                    px[x, y] = (r, g, b, 0)
                elif dist < tol * 2:                      # мягкий край без ореола
                    px[x, y] = (r, g, b, int(a * (dist - tol) / tol))
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else img


SET = (
    [(y, None, "КУБОК", f"{y}_cup.png") for y in ("2010", "2011", "2012", "2013", "2014", "2015")]
    + [(y, None, "КУБОК ФЕДЕРАЦИИ", f"{y}_cup.png") for y in ("2016", "2017", "2018")]
    + [("2009", None, "ПЕРВЕНСТВО", "2009_champ.png"), ("2010", None, "ПЕРВЕНСТВО", "2010_champ.png")]
    + [(y, g, "ПЕРВЕНСТВО", f"{y}_group{g.lower()}_champ.png")
       for y in ("2011", "2012", "2013", "2014", "2015") for g in ("A", "B")]
    + [("2011", None, "КУБОК РОССИИ", "2011_kubokrossii.png")]
    + [("2012", None, "ТЕРРИТОРИЯ ХОККЕЯ U15", "2012_territoriya.png"),
       ("2013", None, "ТЕРРИТОРИЯ ХОККЕЯ U14", "2013_territoriya.png")]
)


def fetch_kr_logo(pick=None):
    """Логотип Кубка России со страницы турнира: показывает картинки-кандидаты и сохраняет выбранную."""
    import io
    import re
    import requests
    sys.path.insert(0, str(BASE))
    import spb_fhr_client as c
    s = c.create_session_kubok_rossii()
    base = f"https://{c.KUBOK_ROSSII_DOMAIN}"
    page = s.get(f"{base}/tournaments/{c.KUBOK_ROSSII_TOURNAMENT_SLUG}/", timeout=25).text
    imgs = []
    for u in re.findall(r'<img[^>]+?(?:data-src|src)="([^"]+)"', page):
        if re.search(r"teams|default|sprite|flag|avatar|icons?/", u) or u in imgs:
            continue
        imgs.append(u if u.startswith("http") else base + u)
    if not imgs:
        print("На странице турнира картинок не нашлось")
        return
    for i, u in enumerate(imgs[:10]):
        print(f"  [{i}] {u}")
    if pick is None:
        pick = next((i for i, u in enumerate(imgs) if re.search(r"tournament|logo|upload|iblock", u, re.I)), 0)
    data = s.get(imgs[pick], timeout=25).content
    Image.open(io.BytesIO(data)).convert("RGBA").save(KR_LOGO_PATH)
    print(f"Сохранён [{pick}] как {KR_LOGO_PATH.name} — откройте и проверьте: open {KR_LOGO_PATH.name}")
    print("Если это не тот логотип, выберите другой номер: python3 generate_banner_v3.py --fetch-kr-logo НОМЕР")


FRIENDLY_SET = ([(str(y), f"friendly_{y}.png") for y in range(2009, 2019)] + [(None, "friendly_unknown.png")])


def main():
    if "--fetch-kr-logo" in sys.argv:
        i = sys.argv.index("--fetch-kr-logo")
        fetch_kr_logo(int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else None)
        return
    out_dir = BASE / "banners_tablo"
    out_dir.mkdir(exist_ok=True)
    for year, group, tournament, name in SET:
        make_banner(year, group, tournament, out_dir / name)
    print(f"Сгенерировано {len(SET)} баннеров в {out_dir}")
    if "--install" in sys.argv:
        live, backup = BASE / "banners", BASE / "banners_before_tablo"
        if live.exists() and not backup.exists():
            shutil.copytree(live, backup)
            print(f"Прежние баннеры сохранены в {backup}")
        live.mkdir(exist_ok=True)
        for *_, name in SET:
            shutil.copy(out_dir / name, live / name)
        print(f"Баннеры «Табло» установлены в {live}. Вернуть прежние: cp {backup}/* {live}/")
    if "--friendly" in sys.argv:                      # баннеры товарищеских игр
        fr_live, fr_backup = BASE / "banners_friendly", BASE / "banners_friendly_before_tablo"
        if fr_live.exists() and not fr_backup.exists():
            shutil.copytree(fr_live, fr_backup)
            print(f"Прежние баннеры товарищеских игр сохранены в {fr_backup}")
        fr_live.mkdir(exist_ok=True)
        for year, name in FRIENDLY_SET:
            make_banner(year, None, "ТОВАРИЩЕСКИЙ", fr_live / name)
        print(f"Баннеры товарищеских игр «Табло» установлены: {len(FRIENDLY_SET)} шт.")


if __name__ == "__main__":
    main()
