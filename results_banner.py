#!/usr/bin/env python3
"""
results_banner.py — «баннер с результатами» для постов дня.

Сверху баннер турнира, под ним строки матчей: время, команды с логотипами,
счёт с пометкой ОТ/ПБ (победитель выделен), несыгранные — «— : —».
Используется post_schedule.py; логотипы берутся из того же справочника,
что и в турнирных таблицах (post_standings.py).
"""
import io
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

BASE = Path(__file__).parent
FONT_BOLD = BASE / "fonts" / "PT_Sans-Web-Bold.ttf"
FONT_REG = BASE / "fonts" / "PT_Sans-Web-Regular.ttf"

W, S = 1280, 2
BG, ROW_ALT = (11, 18, 32), (18, 28, 48)
TEXT, MUTED, DIM = (255, 255, 255), (150, 164, 190), (95, 108, 132)
ACCENT_A, ACCENT_DEFAULT = (255, 61, 90), (0, 194, 255)
DAY_NAMES = {"Пн": "ПН", "Вт": "ВТ", "Ср": "СР", "Чт": "ЧТ", "Пт": "ПТ", "Сб": "СБ", "Вс": "ВС"}
TYPE_NAMES = {"КУБОК": "Кубок СПб", "ПЕРВЕНСТВО": "Первенство СПб"}

_logo_cache = {}


def _font(bold, size):
    try:
        return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REG), size * S)
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size * S)


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


def _fit(draw, text, bold, size, max_w):
    while size > 14:
        f = _font(bold, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return _font(bold, size)


def _goal_line(d, line, x, y, font, anchor, accent):
    """Строка голов или строка вратаря (с цветной меткой «ВРАТАРЬ»)."""
    if isinstance(line, tuple) and line[0] == "goalie":
        label, label_font = "ВРАТАРЬ  ", _font(True, 15)
        text_w = d.textlength(line[1], font=font)
        label_w = d.textlength(label, font=label_font)
        start = x - text_w - label_w if anchor == "ra" else x
        d.text((start, y + 3 * S), label, font=label_font, fill=accent, anchor="la")
        d.text((start + label_w, y), line[1], font=font, fill=TEXT, anchor="la")
    else:
        d.text((x, y), line, font=font, fill=MUTED, anchor=anchor)


def _wrap_goals(draw, goals, font, max_w):
    """Список голов -> строки, переносимые по ширине колонки."""
    lines, cur = [], ""
    for g in goals:
        cand = f"{cur},  {g}" if cur else g
        if cur and draw.textlength(cand, font=font) > max_w:
            lines.append(cur + ",")
            cur = g
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def render(banner_path, matches, date_label, group, title, out_path):
    """Рисует картинку и сохраняет в out_path. matches: [{time, team1, team2, score}]."""
    accent = ACCENT_A if group in ("A", "А") else ACCENT_DEFAULT
    if banner_path and Path(banner_path).exists():
        b = Image.open(banner_path).convert("RGB")
        header = b.resize((W * S, int(b.height * W * S / b.width)), Image.LANCZOS)
    else:
        header = Image.new("RGB", (W * S, 300 * S), BG)

    ROW, TOP, FOOT = 104 * S, 84 * S, 58 * S
    GOAL_LINE, GOAL_PAD = 30 * S, 14 * S
    rows = sorted(matches, key=lambda m: m.get("time") or "")
    cx = W * S // 2
    box_w, box_h, logo = 200 * S, 64 * S, 50 * S
    name_max = cx - box_w // 2 - 18 * S - logo - 16 * S - 118 * S
    goals_w = cx - box_w // 2 - 18 * S - 40 * S          # ширина колонки голов каждой команды
    measure = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    goal_font = _font(False, 20)
    layout = []
    for m in rows:
        g1 = _wrap_goals(measure, m.get("goals1") or [], goal_font, goals_w)
        g2 = _wrap_goals(measure, m.get("goals2") or [], goal_font, goals_w)
        # вратари — на одном уровне у обеих команд, под более длинным списком голов
        if m.get("goalie1") or m.get("goalie2"):
            depth = max(len(g1), len(g2))
            g1 = g1 + [""] * (depth - len(g1))
            g2 = g2 + [""] * (depth - len(g2))
            if m.get("goalie1"):
                g1.append(("goalie", m["goalie1"]))
            if m.get("goalie2"):
                g2.append(("goalie", m["goalie2"]))
        n = max(len(g1), len(g2), 1 if m.get("penalty") else 0)
        layout.append((g1, g2, ROW + (n * GOAL_LINE + GOAL_PAD if n else 0)))
    img = Image.new("RGB", (W * S, header.height + TOP + sum(h for _, _, h in layout) + FOOT), BG)
    img.paste(header, (0, 0))
    d = ImageDraw.Draw(img)

    y = header.height
    d.rectangle([0, y + TOP - 4 * S, W * S, y + TOP], fill=accent)
    parts = date_label.split()
    dow, date = parts[0], parts[-1][:5]
    d.text((40 * S, y + TOP // 2 - 2 * S), f"РЕЗУЛЬТАТЫ  ·  {DAY_NAMES.get(dow, dow)} {date}",
           font=_font(True, 34), fill=TEXT, anchor="lm")
    d.text((W * S - 40 * S, y + TOP // 2 - 2 * S), title, font=_font(False, 24), fill=MUTED, anchor="rm")
    y += TOP

    for i, m in enumerate(rows):
        g1_lines, g2_lines, row_h = layout[i]
        if i % 2:
            d.rectangle([0, y, W * S, y + row_h], fill=ROW_ALT)
        mid = y + ROW // 2
        d.text((32 * S, mid), m.get("time") or "", font=_font(False, 24), fill=DIM, anchor="lm")

        sc = split_score(m.get("score"))
        t1, t2 = _display(m["team1"]), _display(m["team2"])
        win1, win2 = bool(sc and sc[0] > sc[1]), bool(sc and sc[1] > sc[0])

        d.rounded_rectangle([cx - box_w // 2, mid - box_h // 2, cx + box_w // 2, mid + box_h // 2],
                            radius=14 * S, fill=accent if sc else ROW_ALT,
                            outline=None if sc else DIM, width=2 * S)
        if sc:
            shift = 16 * S if sc[2] else 0
            d.text((cx - shift, mid), f"{sc[0]} : {sc[1]}", font=_font(True, 38), fill=BG, anchor="mm")
            if sc[2]:
                d.text((cx + box_w // 2 - 14 * S, mid + 2 * S), sc[2], font=_font(True, 18), fill=BG, anchor="rm")
        else:
            d.text((cx, mid), "—  :  —", font=_font(True, 30), fill=DIM, anchor="mm")

        lx = cx - box_w // 2 - 18 * S - logo
        l1 = _logo(m["team1"], logo)
        if l1:
            img.paste(l1, (lx + (logo - l1.width) // 2, mid - l1.height // 2), l1)
        d.text((lx - 16 * S, mid), t1, font=_fit(d, t1, win1, 29, name_max),
               fill=TEXT if (win1 or not sc) else MUTED, anchor="rm")

        rx = cx + box_w // 2 + 18 * S
        l2 = _logo(m["team2"], logo)
        if l2:
            img.paste(l2, (rx + (logo - l2.width) // 2, mid - l2.height // 2), l2)
        d.text((rx + logo + 16 * S, mid), t2, font=_fit(d, t2, win2, 29, name_max),
               fill=TEXT if (win2 or not sc) else MUTED, anchor="lm")

        # авторы голов: под командой 1 — справа налево к счёту, под командой 2 — от счёта
        gy = y + ROW - 6 * S
        for k, line in enumerate(g1_lines):
            _goal_line(d, line, cx - box_w // 2 - 18 * S, gy + k * GOAL_LINE, goal_font, "ra", accent)
        for k, line in enumerate(g2_lines):
            _goal_line(d, line, cx + box_w // 2 + 18 * S, gy + k * GOAL_LINE, goal_font, "la", accent)
        if m.get("penalty"):
            p1, p2 = m["penalty"]
            d.text((cx, gy), f"штраф  {p1} : {p2}", font=_font(False, 18), fill=DIM, anchor="ma")
        y += row_h

    d.text((W * S - 40 * S, y + FOOT // 2), "fhspb.ru  ·  spb.fhr.ru", font=_font(False, 20), fill=DIM, anchor="rm")
    img = img.resize((W, img.height // S), Image.LANCZOS)
    tmp = f"{out_path}.tmp"
    img.save(tmp, "PNG")
    Path(tmp).replace(out_path)
    return out_path
