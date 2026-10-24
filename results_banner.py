#!/usr/bin/env python3
"""
results_banner.py — баннер с результатами дня в стиле «Табло».

Сверху баннер турнира, под ним панели матчей: время, команды с логотипами,
счёт светящимися точками (жёлтый — итог, красный — идёт матч, тусклые
прочерки — ещё не начался), «ОВЕРТАЙМ»/«БУЛЛИТЫ», штраф, авторы голов с
передачами, вратари. Используется post_schedule.py.

Ключи матча: time, team1, team2, score, goals1/2, goalie1/2, penalty, live.
"""
import io
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
FONT_BOLD = BASE / "fonts" / "PT_Sans-Web-Bold.ttf"
FONT_REG = BASE / "fonts" / "PT_Sans-Web-Regular.ttf"

W, S = 1280, 2
BG, PANEL, EDGE, SCREEN = (8, 11, 18), (17, 21, 31), (48, 56, 74), (6, 8, 12)
TEXT, MUTED, DIM = (240, 244, 250), (140, 152, 176), (96, 106, 128)
AMBER, AMBER_DIM = (255, 200, 50), (130, 100, 40)
RED = (255, 72, 72)
DAY_NAMES = {"Пн": "ПН", "Вт": "ВТ", "Ср": "СР", "Чт": "ЧТ", "Пт": "ПТ", "Сб": "СБ", "Вс": "ВС"}
TYPE_NAMES = {"КУБОК": "Кубок СПб", "ПЕРВЕНСТВО": "Первенство СПб"}
SUFFIX_TEXT = {"ОТ": "ОВЕРТАЙМ", "ПБ": "БУЛЛИТЫ", "Б": "БУЛЛИТЫ"}

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
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
}

_logo_cache = {}


def _font(bold, size):
    try:
        return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), int(size * S))
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", int(size * S))


def split_score(score):
    """'4 : 3ОТ' -> (4, 3, 'ОТ'); None, если счёта нет."""
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*(\S*)", score or "")
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else None


def results_title(age, group, tournament_type):
    if tournament_type == "КУБОК" and age in ("2016", "2017", "2018"):
        name = "Кубок Федерации"
    else:
        name = TYPE_NAMES.get(tournament_type, tournament_type)
    letter = {"A": "А", "B": "Б"}.get(group, group)
    return f"{name} {age} г.р." + (f" · группа {letter}" if letter else "")


def _display(name):
    try:
        import post_standings as st
        return st._fhspb_display_name(name)
    except Exception:
        return re.sub(r"\s(?:09|1[0-8])(?=(?:\s\d)?$)", "", name).strip()


def _logo(raw_name, size):
    display = _display(raw_name)
    if (display, size) in _logo_cache:
        return _logo_cache[(display, size)]
    img = None
    try:
        import post_standings as st
        local = getattr(st, "LOCAL_LOGO_OVERRIDES", {}).get(display)
        if local:
            img = Image.open(st.LOCAL_LOGOS_DIR / local).convert("RGBA")
        else:
            url = st._load_logo_map().get(st._logo_key(raw_name))
            if url:
                img = Image.open(io.BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")
        if img:
            img.thumbnail((size, size), Image.LANCZOS)
    except Exception:
        img = None
    _logo_cache[(display, size)] = img
    return img


def _led(draw, text, x, y, cell, color, dot=0.84):
    for ch in text:
        for r, row in enumerate(GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    cx, cy = x + c * cell, y + r * cell
                    draw.ellipse([cx, cy, cx + cell * dot, cy + cell * dot], fill=color)
        x += cell * (6.2 if ch != ":" else 4.4)


def _led_width(text, cell):
    return sum(cell * (6.2 if ch != ":" else 4.4) for ch in text) - cell * 1.2


def _wrap(draw, items, font, max_w):
    lines, cur = [], ""
    for g in items:
        cand = f"{cur},  {g}" if cur else g
        if cur and draw.textlength(cand, font=font) > max_w:
            lines.append(cur + ",")
            cur = g
        else:
            cur = cand
    return lines + ([cur] if cur else [])


def _fit(draw, text, size, max_w):
    while size > 14:
        f = _font(True, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return _font(True, size)


def render(banner_path, matches, date_label, group, title, out_path):
    """Рисует баннер с результатами и сохраняет в out_path."""
    width = W * S
    if banner_path and Path(banner_path).exists():
        b = Image.open(banner_path).convert("RGB")
        header = b.resize((width, int(b.height * width / b.width)), Image.LANCZOS)
    else:
        header = Image.new("RGB", (width, 277 * S), BG)

    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    gfont = _font(False, 19)
    cx = width // 2
    plate_w, plate_h = 300 * S, 108 * S
    col_w = cx - plate_w // 2 - 60 * S
    rows = []
    for m in sorted(matches, key=lambda x: x.get("time") or ""):
        g1 = _wrap(measure, m.get("goals1") or [], gfont, col_w)
        g2 = _wrap(measure, m.get("goals2") or [], gfont, col_w)
        if m.get("goalie1") or m.get("goalie2"):
            n = max(len(g1), len(g2))
            g1 += [""] * (n - len(g1))
            g2 += [""] * (n - len(g2))
            g1.append(("goalie", m.get("goalie1") or ""))
            g2.append(("goalie", m.get("goalie2") or ""))
        extra = max(len(g1), len(g2))
        room = extra * 28 + 24 if extra else (40 if m.get("penalty") else 0)   # место под штраф без голов
        rows.append((m, g1, g2, (144 + room) * S))

    top = 76 * S
    total_h = header.height + top + sum(r[3] + 14 * S for r in rows) + 56 * S
    img = Image.new("RGBA", (width, total_h), BG + (255,))
    img.paste(header, (0, 0))
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    lit = []
    d = ImageDraw.Draw(img)

    parts = (date_label or "").split()
    day = f"{DAY_NAMES.get(parts[0], parts[0])} {parts[-1][:5]}" if len(parts) >= 2 else date_label
    y = header.height
    d.text((36 * S, y + top // 2), f"РЕЗУЛЬТАТЫ  ·  {day}", font=_font(True, 32), fill=AMBER, anchor="lm")
    d.text((width - 36 * S, y + top // 2), title, font=_font(False, 22), fill=MUTED, anchor="rm")
    y += top

    for m, g1, g2, rh in rows:
        d.rounded_rectangle([20 * S, y, width - 20 * S, y + rh], radius=16 * S, fill=PANEL, outline=EDGE, width=2 * S)
        mid = y + 68 * S
        d.text((44 * S, y + 22 * S), m.get("time") or "", font=_font(True, 22), fill=AMBER)

        px0, py0 = cx - plate_w // 2, mid - plate_h // 2
        d.rounded_rectangle([px0, py0, px0 + plate_w, py0 + plate_h], radius=10 * S, fill=SCREEN, outline=EDGE, width=2 * S)
        sc = split_score(m.get("score"))
        live = m.get("live")
        text = f"{sc[0]}:{sc[1]}" if sc else "-:-"
        under = (live and sc) or (sc and sc[2])
        # С подписью под счётом цифры чуть меньше, чтобы всё помещалось в табло
        cell = (9 if under else 11) * S
        sx = cx - _led_width(text, cell) / 2
        sy = py0 + 12 * S if under else mid - 3.5 * cell
        if live and sc:
            _led(gdraw, text, sx, sy, cell, (255, 40, 40, 170))
            lit.append((text, sx, sy, cell, RED))
            d.text((cx, py0 + plate_h - 14 * S), "LIVE" if live is True else f"LIVE · {live}",
                   font=_font(True, 15), fill=(255, 90, 90), anchor="mm")
        elif sc:
            _led(gdraw, text, sx, sy, cell, (255, 160, 0, 170))
            lit.append((text, sx, sy, cell, AMBER))
            if sc[2]:
                d.text((cx, py0 + plate_h - 14 * S), SUFFIX_TEXT.get(sc[2], sc[2]),
                       font=_font(True, 15), fill=AMBER, anchor="mm")
        else:
            lit.append((text, sx, sy, cell, AMBER_DIM))

        final = bool(sc) and not live
        win1 = bool(final and sc[0] > sc[1])
        win2 = bool(final and sc[1] > sc[0])
        t1, t2 = _display(m["team1"]).upper(), _display(m["team2"]).upper()
        lg = 52 * S
        name_max = px0 - 22 * S - lg - 18 * S - 44 * S     # время матча стоит выше, место до края панели

        lx = px0 - 22 * S - lg
        l1 = _logo(m["team1"], lg)
        if l1:
            img.alpha_composite(l1, (lx + (lg - l1.width) // 2, mid - l1.height // 2))
        d.text((lx - 18 * S, mid), t1, font=_fit(d, t1, 30, name_max),
               fill=TEXT if (win1 or not final) else MUTED, anchor="rm")
        rx = px0 + plate_w + 22 * S
        l2 = _logo(m["team2"], lg)
        if l2:
            img.alpha_composite(l2, (rx + (lg - l2.width) // 2, mid - l2.height // 2))
        d.text((rx + lg + 18 * S, mid), t2, font=_fit(d, t2, 30, name_max),
               fill=TEXT if (win2 or not final) else MUTED, anchor="lm")

        if m.get("penalty"):
            p1, p2 = m["penalty"]
            d.text((cx, py0 + plate_h + 14 * S), f"ШТРАФ  {p1} : {p2}", font=_font(False, 17), fill=DIM, anchor="mt")
        gy = py0 + plate_h + 22 * S
        label_font = _font(True, 15)
        label_w = d.textlength("ВРАТАРЬ  ", font=label_font)
        for k, line in enumerate(g1):
            yy = gy + k * 28 * S
            if isinstance(line, tuple):
                if line[1]:
                    tw = d.textlength(line[1], font=gfont)
                    d.text((px0 - 22 * S - tw - label_w, yy + 3 * S), "ВРАТАРЬ  ", font=label_font, fill=AMBER)
                    d.text((px0 - 22 * S - tw, yy), line[1], font=gfont, fill=TEXT)
            elif line:
                d.text((px0 - 22 * S, yy), line, font=gfont, fill=MUTED, anchor="ra")
        for k, line in enumerate(g2):
            yy = gy + k * 28 * S
            if isinstance(line, tuple):
                if line[1]:
                    d.text((rx, yy + 3 * S), "ВРАТАРЬ  ", font=label_font, fill=AMBER)
                    d.text((rx + label_w, yy), line[1], font=gfont, fill=TEXT)
            elif line:
                d.text((rx, yy), line, font=gfont, fill=MUTED)
        y += rh + 14 * S

    d.text((width - 36 * S, total_h - 28 * S), "fhspb.ru  ·  spb.fhr.ru", font=_font(False, 18), fill=DIM, anchor="rm")
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(10 * S)))
    d = ImageDraw.Draw(img)
    for text, sx, sy, cell, color in lit:          # цифры поверх свечения — чёткие
        _led(d, text, sx, sy, cell, color)
    img = img.convert("RGB").resize((W, total_h // S), Image.LANCZOS)
    tmp = f"{out_path}.tmp"
    img.save(tmp, "PNG")
    Path(tmp).replace(out_path)
    return out_path
