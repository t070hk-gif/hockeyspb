#!/usr/bin/env python3
"""
Итоги 2026 года по годам рождения (Первенство СПб и Кубок Федерации) —
картинки в стиле «Табло», в личку администратору.

Источник — spb.fhr.ru: календарь по группам и страница каждого матча
(счёт по периодам → овертаймы/буллиты, протокол → штрафные минуты).
Сыгранные матчи запоминаются в year_stats_cache.json, повторный сбор быстрый.

    python3 year_stats.py                    — собрать по сегодняшний день и прислать в личку
    python3 year_stats.py --to 24.10.2026    — по указанную дату
    python3 year_stats.py --preview          — только нарисовать картинки в year_stats/, не отправлять
    python3 year_stats.py --monthly          — для cron: работает только в последний день месяца
    python3 year_stats.py --stages           — какие группы и этапы (в т. ч. финальные) попадают в итоги
    python3 year_stats.py --publish-test     — показать в личке посты 31 декабря (итоги по темам) и поздравление
"""
import base64
import html as H
import io
import json
import re
import sys
import time
import urllib.parse
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import spb_fhr_client
import spb_protocol
import generate_banner_v3 as tb
import festive
from config import TG_BOT_TOKEN, TG_CHAT_ID, ADMIN_ID
with redirect_stdout(io.StringIO()):
    import post_schedule as ps

YEAR = 2026
CACHE_FILE = BASE / "year_stats_cache.json"
OUT_DIR = BASE / "year_stats"

# Сезон 2025/26 (январь–апрель): один турнир, годы рождения — фильтр календаря
PREV_SEASON = [
    ("16731969", "pervenstvo-spb-16731969", "ПЕРВЕНСТВО", {
        "2008": "16731987", "2009": "16731994", "2010": "16731998", "2011": "16732030",
        "2012": "16732031", "2013": "16732033", "2014": "16732039"}),
    ("16732040", "kubok-federatsii-spb-16732040", "КУБОК ФЕДЕРАЦИИ", {
        "2015": "16732041", "2016": "16732043", "2017": "16732062"}),
]
# Сезон 2026/27 (с сентября): у каждого года своя страница
CUR_SEASON = [
    ("24813508", "pervenstvo-spb-24813508", "ПЕРВЕНСТВО", {
        "2009": "24813510", "2010": "24813512", "2011": "24813519", "2012": "24813565",
        "2013": "24813568", "2014": "24813569", "2015": "24813584"}),
    ("24813588", "kubok-federatsii-spb-24813588", "КУБОК ФЕДЕРАЦИИ", {
        "2016": "24813589", "2017": "24813590", "2018": "24813594"}),
]
PREV_LABEL = "янв–апр"
METRICS = [("games", "Матчей"), ("goals", "Шайб забито"), ("pim", "Штрафных минут"),
           ("ot", "Овертаймов"), ("so", "Буллитов"), ("shutouts", "Игр всухую")]
OPTIONAL = {"ot", "so"}                     # строки без единого случая не показываем


# ----------------------------------------------------------------- spb.fhr.ru
def _decode(link):
    """Параметры кнопки фильтра: {'TOURNAMENT_ID': …, 'GROUP_ID': …, 'YEAR_ID': …}.
    Устойчиво к &amp;amp;, кодированию адреса и вариантам base64."""
    # Не html.unescape: он принимает «&para» в «&params=» за символ «¶» и портит ссылку
    text = link
    while "&amp;" in text:
        text = text.replace("&amp;", "&")
    m = re.search(r"params=([^&\"'\s]+)", text)
    if not m:
        return {}
    raw0 = m.group(1)
    for raw in (urllib.parse.unquote(raw0), raw0, urllib.parse.unquote_plus(raw0)):
        for decoder in (base64.b64decode, base64.urlsafe_b64decode):
            try:
                dec = decoder(raw + "=" * (-len(raw) % 4)).decode(errors="ignore")
            except Exception:
                continue
            found = dict(re.findall(r's:\d+:"([A-Z_]+)";s:\d+:"(\d*)"', dec))
            if found.get("GROUP_ID"):
                return found
    return {}


def groups_from_html(page, year_id=None):
    """[(подпись, GROUP_ID)] из кнопок фильтра: группы и этапы («За 1-4 место», «Переходный турнир»…).
    Подпись — первый текст после кнопки (до следующей кнопки), в какие бы теги он ни был обёрнут."""
    out = []
    for m in re.finditer(r'data-ajax-link="([^"]+)"', page):
        params = _decode(m.group(1))
        gid = params.get("GROUP_ID")
        if not gid or gid in [g for _, g in out]:
            continue
        if year_id and params.get("YEAR_ID") and params["YEAR_ID"] != year_id:
            continue                                     # кнопка другого года рождения
        seg = page[m.end(): m.end() + 800]
        nxt = seg.find("data-ajax-link")
        seg = seg[:nxt] if nxt > 0 else seg
        texts = [re.sub(r"\s+", " ", t).strip() for t in re.findall(r">([^<]*)<", seg)]
        label = next((t for t in texts if t and len(t) <= 40), "")
        out.append((label or f"Группа {len(out) + 1}", gid))
    return out


def _bot_groups(session, slug, year_id):
    """Запасной путь — номера групп способом основного бота (подписи «Группа 1», «Группа 2»…)."""
    try:
        ids = ps._spb_group_ids(session, slug, year_id) or []
    except Exception:
        ids = []
    return [(f"Группа {i + 1}", g) for i, g in enumerate(ids)]


def prev_groups(session, slug, year_id):
    """Группы и этапы года в сезоне 2025/26. Группы — на странице года рождения, финальные этапы
    («За 1-4 место», «Переходный турнир»…) — только в общем календаре турнира, переключённом на год."""
    found = []

    def add(items):
        for label, gid in items:
            if gid not in [g for _, g in found]:
                found.append((label, gid))

    add(groups_from_html(session.get(f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/", timeout=25).text, year_id))
    cal_url = f"https://spb.fhr.ru/tournaments/{slug}/calendar/"
    cal = session.get(cal_url, timeout=25).text
    add(groups_from_html(cal, year_id))                  # календарь открыт на этом году по умолчанию
    for attrs, label in re.findall(r"<option([^>]*)>\s*([^<]{1,20}?)\s*</option>", cal):
        val = re.search(r'value="(\d+)"', attrs)
        url = re.search(r'data-ajax="([^"]+)"', attrs)
        if val and url and val.group(1) == year_id:
            u = url.group(1).replace("&amp;", "&")
            u = u if u.startswith("http") else "https://spb.fhr.ru" + u
            resp = session.get(u, timeout=25, headers={"X-Requested-With": "XMLHttpRequest", "Referer": cal_url})
            try:
                text = json.dumps(resp.json(), ensure_ascii=False).replace("\\/", "/").replace('\\"', '"')
            except Exception:
                text = resp.text
            add(groups_from_html(text, year_id))
    return found or _bot_groups(session, slug, year_id)


def cur_groups(session, slug, year_id):
    page = session.get(f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/", timeout=25).text
    groups = groups_from_html(page, year_id) or _bot_groups(session, slug, year_id)
    return groups or [("Все", None)]


DETAILS_VERSION = 2
_ASSIST_FULL = re.compile(r"\d+\.\s*([А-ЯЁA-Z][А-ЯЁа-яёA-Za-z\-]+(?:\s+[А-ЯЁA-Z][а-яёa-z\-]+)?)")


def parse_details(html):
    """Счёт по периодам, штрафные минуты, авторы голов, передачи, вратари из страницы матча."""
    periods = [f"{a}:{b}" for a, b in spb_fhr_client.PERIOD_SCORE_RE.findall(html)]
    try:
        summ = spb_protocol.summarize(html)
        events = spb_protocol.parse_events(html)
    except Exception:
        summ, events = {}, []
    pen = summ.get("penalty") or (0, 0)
    scorers, assists = [], []
    for e in events:
        if e["kind"] in ("", "goal") and re.fullmatch(r"\d+", e.get("label") or ""):
            for card in (e["left"], e["right"]):
                if card and card.get("name"):
                    scorers.append([card["name"], card.get("team", "")])
                    for a in _ASSIST_FULL.findall(card.get("label", "")):
                        assists.append([a.strip(), card.get("team", "")])
    full = {}
    for e in events:
        if e["kind"] == "keepers" or (e.get("label") or "").lower().startswith("вратар"):
            for card in (e["left"], e["right"]):
                if card and card.get("name"):
                    full[card["name"].split()[0]] = card["name"]
    keepers = {}
    for side in (1, 2):
        g = (summ.get("goalies") or {}).get(side) or []
        keepers[str(side)] = [[full.get(n, n), int(conceded)] for n, conceded in g]
    return {"v": DETAILS_VERSION, "periods": periods, "pim": int(pen[0]) + int(pen[1]),
            "scorers": scorers, "assists": assists, "keepers": keepers,
            "teams": {str(k): v for k, v in (summ.get("teams") or {}).items()}}


def game_details(session, game_id, cache):
    """Подробности матча (сыгранные запоминаются; старые записи без имён перечитываются)."""
    if cache.get(game_id, {}).get("v") == DETAILS_VERSION:
        return cache[game_id]
    html = session.get(f"https://spb.fhr.ru/games/{game_id}/", timeout=25,
                       headers={"Referer": "https://spb.fhr.ru/tournaments/"}).text
    cache[game_id] = parse_details(html)
    time.sleep(0.3)
    return cache[game_id]


# ----------------------------------------------------------------- подсчёт
def collect(date_to):
    try:
        cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    session = spb_fhr_client.create_session()
    date_from = datetime(YEAR, 1, 1)
    stats = {}                                  # возраст -> столбец -> показатели
    tour_of = {}
    games_of = {}                               # возраст -> список матчей для рекордов
    jobs = [("prev", t) for t in PREV_SEASON] + [("cur", t) for t in CUR_SEASON]
    for season, (tid, slug, tour, years) in jobs:
        for age, year_id in years.items():
            groups = prev_groups(session, slug, year_id) if season == "prev" else cur_groups(session, slug, year_id)
            for label, gid in groups:
                column = PREV_LABEL if season == "prev" else label.replace("Группа ", "Гр. ")
                rows = ps._spb_calendar_rows(session, tid, slug, year_id, gid)
                n = 0
                for g in rows:
                    try:
                        d = datetime.strptime(g["date"], "%d.%m.%Y")
                    except Exception:
                        continue
                    sc = re.match(r"\s*(\d+)\s*:\s*(\d+)", g.get("score") or "")
                    if not sc or not (date_from <= d <= date_to):
                        continue
                    info = game_details(session, g["game_id"], cache)
                    a, b = int(sc.group(1)), int(sc.group(2))
                    suffix = ps._overtime_suffix(info["periods"]) or ""
                    col = stats.setdefault(age, {}).setdefault(column, {k: 0 for k, _ in METRICS})
                    col["games"] += 1
                    col["goals"] += a + b - (1 if suffix == "ПБ" else 0)      # победный буллит — не шайба
                    col["pim"] += info["pim"]
                    col["ot"] += suffix == "ОТ"
                    col["so"] += suffix == "ПБ"
                    col["shutouts"] += (min(a, b) == 0 and suffix != "ПБ")
                    games_of.setdefault(age, []).append({"date": d, "time": g.get("time") or "", "team1": g["team1"],
                                                         "team2": g["team2"], "a": a, "b": b, "suffix": suffix, "info": info})
                    n += 1
                tour_of[age] = tour if season == "cur" or age not in tour_of else tour_of[age]
                print(f"   {age} {season} {label}: {n} матчей")
                CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return stats, tour_of, games_of


# ----------------------------------------------------------------- картинка
S = 2
TEXT, MUTED, AMBER = (240, 244, 250), (140, 152, 176), (255, 200, 50)
BG, PANEL, PANEL2, EDGE = (8, 11, 18), (17, 21, 31), (13, 17, 26), (48, 56, 74)
FB, FR = str(BASE / "fonts" / "PT_Sans-Web-Bold.ttf"), str(BASE / "fonts" / "PT_Sans-Web-Regular.ttf")


def _f(size, bold=True):
    return ImageFont.truetype(FB if bold else FR, int(size * S))


def _led(d, text, x, y, cell, color):
    for ch in text:
        for r, row in enumerate(tb.GLYPHS[ch]):
            for c, bit in enumerate(row):
                if bit == "1":
                    d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * 0.84, y + r * cell + cell * 0.84], fill=color)
        x += cell * 6.2



# ----------------------------------------------------------------- новогодняя шапка
SNOWFLAKE = ["1001001", "0101010", "0011100", "1111111", "0011100", "0101010", "1001001"]
TREE = ["00000100000", "00001110000", "00011111000", "00111111100", "00001110000", "00011111000",
        "00111111100", "01111111110", "00011111000", "00111111100", "01111111110", "11111111111",
        "00001110000"]
BULBS = [(255, 70, 70), (70, 220, 110), (255, 200, 50), (80, 170, 255), (255, 120, 220)]


def _dots(d, pattern, x, y, cell, color_at, dot=0.8):
    for r, row in enumerate(pattern):
        for c, bit in enumerate(row):
            if bit == "1":
                col = color_at(r, c)
                d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * dot, y + r * cell + cell * dot], fill=col)


def festive_header(age, tour, width=1280):
    """Праздничная шапка итогов: гирлянда, ёлка и снежинки точками табло."""
    import math
    import random
    rnd = random.Random(int(age))
    W, Hh = width * S, 300 * S
    img = Image.new("RGBA", (W, Hh), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    for y in range(Hh):                                       # ночное небо
        t = y / Hh
        d.line([(0, y), (W, y)], fill=(int(8 + 10 * t), int(12 + 16 * t), int(26 + 26 * t), 255))
    for _ in range(140):                                      # мелкий снег
        x, y, r = rnd.randrange(W), rnd.randrange(Hh), rnd.choice((2, 3, 4)) * S // 2
        a = rnd.randrange(50, 150)
        d.ellipse([x, y, x + r, y + r], fill=(220, 235, 255, a))
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for sx, sy, cell, a in ((640, 70, 4, 170), (820, 205, 3, 120), (360, 230, 3, 110), (1235, 230, 3, 130),
                            (560, 200, 2, 90), (1040, 60, 2, 100)):
        _dots(d, SNOWFLAKE, sx * S, sy * S, cell * S, lambda r, c: (210, 230, 255, a))
    # гирлянда: провод и лампочки
    pts = [(x * S, int((22 + 14 * math.sin(x / 70.0)) * S)) for x in range(0, width + 1, 8)]
    d.line(pts, fill=(60, 70, 90, 255), width=2 * S)
    for i, x in enumerate(range(20, width, 46)):
        y = int((22 + 14 * math.sin(x / 70.0)) * S)
        col = BULBS[i % len(BULBS)]
        gd.ellipse([x * S - 12 * S, y - 4 * S, x * S + 12 * S, y + 20 * S], fill=col + (200,))
        d.ellipse([x * S - 6 * S, y + 2 * S, x * S + 6 * S, y + 16 * S], fill=col + (255,))
    # корпус табло с годом
    d.rounded_rectangle([20 * S, 58 * S, 760 * S, 282 * S], radius=18 * S, fill=(20, 24, 34, 255),
                        outline=(52, 60, 78, 255), width=3 * S)
    label = "КУБОК ФЕДЕРАЦИИ" if tour == "КУБОК ФЕДЕРАЦИИ" else "ПЕРВЕНСТВО СПБ"
    plate = (255, 176, 0) if tour == "КУБОК ФЕДЕРАЦИИ" else (233, 30, 85)
    pf = _f(26)
    d.rounded_rectangle([44 * S, 74 * S, 44 * S + d.textlength(label, font=pf) + 36 * S, 116 * S], radius=8 * S, fill=plate)
    d.text((62 * S, 95 * S), label, font=pf, fill=(20, 20, 20) if tour == "КУБОК ФЕДЕРАЦИИ" else (255, 255, 255), anchor="lm")
    cell = 18 * S
    x = 54 * S
    for ch in str(age):
        _dots(gd, tb.GLYPHS[ch], x, 136 * S, cell, lambda r, c: (255, 170, 0, 255))
        _dots(d, tb.GLYPHS[ch], x, 136 * S, cell, lambda r, c: (255, 196, 40, 255))
        x += cell * 6.2
    # ёлка из точек: зелёная, звезда, шарики
    ornaments = {(r, c): BULBS[(r * 7 + c) % len(BULBS)] for r in range(2, 12) for c in range(11)
                 if TREE[r][c] == "1" and rnd.random() < 0.22}
    def tree_color(r, c):
        if r == 0:
            return (255, 210, 60, 255)
        if r == 12:
            return (140, 90, 50, 255)
        return ornaments.get((r, c), (40, 190, 90)) + (255,)
    tx, ty, tc = 850 * S, 74 * S, 16 * S
    _dots(gd, TREE[:1], tx, ty, tc, lambda r, c: (255, 200, 40, 255))
    for (r, c), col in ornaments.items():
        gd.ellipse([tx + c * tc - 4 * S, ty + r * tc - 4 * S, tx + c * tc + tc, ty + r * tc + tc], fill=col + (170,))
    _dots(d, TREE, tx, ty, tc, tree_color)
    # эмблема федерации
    try:
        logo = Image.open(BASE / "fhspb_logo.png").convert("RGBA").resize((130 * S, 130 * S), Image.LANCZOS)
        cx, cy = 1150 * S, 170 * S
        d.ellipse([cx - 72 * S, cy - 72 * S, cx + 72 * S, cy + 72 * S], fill=(255, 255, 255, 255))
        img.alpha_composite(logo, (cx - 65 * S, cy - 65 * S))
    except Exception:
        pass
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(9 * S)))
    d = ImageDraw.Draw(img)
    x = 54 * S
    for ch in str(age):                                         # цифры поверх свечения
        _dots(d, tb.GLYPHS[ch], x, 136 * S, cell, lambda r, c: (255, 196, 40, 255))
        x += cell * 6.2
    _dots(d, TREE, tx, ty, tc, tree_color)
    return img.convert("RGB")


def render(age, columns, tour, period_text, out):
    W = 1280
    order = [c for c in columns if c == PREV_LABEL] + sorted(c for c in columns if c != PREV_LABEL)
    total = {k: sum(columns[c][k] for c in order) for k, _ in METRICS}
    metrics = [(k, name) for k, name in METRICS if k not in OPTIONAL or total[k] > 0]
    hdr = festive_header(age, tour, W)
    rh, top = 92 * S, 84 * S
    head_h = 50 * S
    H = hdr.height + top + head_h + rh * len(metrics) + 70 * S
    img = Image.new("RGBA", (W * S, H), BG + (255,))
    img.paste(hdr, (0, 0))
    d = ImageDraw.Draw(img)
    y = hdr.height
    d.text((36 * S, y + 40 * S), f"ИТОГИ {YEAR}", font=_f(34), fill=AMBER, anchor="lm")
    tw = d.textlength(f"ИТОГИ {YEAR}", font=_f(34))
    _dots(d, SNOWFLAKE, 36 * S + tw + 18 * S, y + 40 * S - 14 * S, 4 * S, lambda r, c: (210, 230, 255))
    d.text((W * S - 36 * S, y + 40 * S), period_text, font=_f(22, False), fill=MUTED, anchor="rm")
    y += top
    label_w = 330
    cols = order + ["Всего"]
    col_w = (W - 40 - label_w) / len(cols)
    xs = [(20 + label_w + col_w * (i + 0.5)) * S for i in range(len(cols))]
    for x, c in zip(xs, cols):
        d.text((x, y + head_h // 2), c.upper(), font=_f(19), fill=AMBER if c == "Всего" else MUTED, anchor="mm")
    y += head_h
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lit = []
    for i, (key, name) in enumerate(metrics):
        d.rounded_rectangle([20 * S, y + 4 * S, W * S - 20 * S, y + rh - 4 * S], radius=12 * S,
                            fill=PANEL if i % 2 == 0 else PANEL2, outline=EDGE, width=S)
        mid = y + rh // 2
        d.text((44 * S, mid), name, font=_f(26), fill=TEXT, anchor="lm")
        for x, c in zip(xs[:-1], order):
            d.text((x, mid), str(columns[c][key]), font=_f(26, False), fill=TEXT, anchor="mm")
        val = str(total[key])
        cell = 6 * S
        while len(val) * cell * 6.2 > col_w * S - 16 * S and cell > 3 * S:
            cell -= S
        vx = xs[-1] - (len(val) * cell * 6.2 - cell * 1.2) / 2
        _led(gd, val, vx, mid - 3.5 * cell, cell, (255, 160, 0, 170))
        lit.append((val, vx, mid - 3.5 * cell, cell))
        y += rh
    d.text((36 * S, H - 32 * S), "Первенство СПб и Кубок Федерации · данные spb.fhr.ru", font=_f(18, False), fill=MUTED, anchor="lm")
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(8 * S)))
    d = ImageDraw.Draw(img)
    for val, vx, vy, cell in lit:
        _led(d, val, vx, vy, cell, AMBER)
    img.convert("RGB").resize((W, H // S), Image.LANCZOS).save(out)
    return out


# ----------------------------------------------------------------- рекорды года
def _team(raw):
    try:
        return ps._spb_display_name(raw, "").strip()
    except Exception:
        return raw


def records(games):
    """Бомбардиры, ассистенты, вратари «на ноль», крупнейшая победа, самая результативная игра, серия побед."""
    from collections import Counter
    scorers = Counter((n, _team(t)) for g in games for n, t in g["info"].get("scorers", []))
    assists = Counter((n, _team(t)) for g in games for n, t in g["info"].get("assists", []))
    zeros = Counter()
    for g in games:
        for side in ("1", "2"):
            ks = g["info"].get("keepers", {}).get(side) or []
            if len(ks) == 1 and ks[0][1] == 0:
                team = g["team1"] if side == "1" else g["team2"]          # сторона 1 — первая команда календаря
                zeros[(ks[0][0], _team(team))] += 1
    goals = lambda g: g["a"] + g["b"] - (1 if g["suffix"] == "ПБ" else 0)
    biggest = max(games, key=lambda g: (abs(g["a"] - g["b"]), goals(g)), default=None)
    richest = max(games, key=lambda g: (goals(g), -abs(g["a"] - g["b"])), default=None)
    streak, run = (None, 0), {}
    for g in sorted(games, key=lambda g: (g["date"], g["time"])):
        for team, mine, theirs in ((g["team1"], g["a"], g["b"]), (g["team2"], g["b"], g["a"])):
            key = ps.normalize_team_name(team)
            run[key] = run.get(key, 0) + 1 if mine > theirs else 0
            if run[key] > streak[1]:
                streak = (_team(team), run[key])
    top = lambda cnt: [(n, t, k) for (n, t), k in sorted(cnt.items(), key=lambda x: (-x[1], x[0][0]))[:3] if k > 0]
    game_text = lambda g: f"{_team(g['team1'])} — {_team(g['team2'])}  {g['a']}:{g['b']}{(' ' + g['suffix']) if g['suffix'] else ''}  ·  {g['date']:%d.%m}"
    return {"scorers": top(scorers), "assists": top(assists), "zeros": top(zeros),
            "biggest": game_text(biggest) if biggest else "", "richest": game_text(richest) if richest else "",
            "streak": f"{streak[0]} — {streak[1]} {_wins_word(streak[1])} подряд" if streak[0] else ""}


def _wins_word(n):
    if n % 10 == 1 and n % 100 != 11:
        return "победа"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "победы"
    return "побед"


def render_records(age, rec, tour, period_text, out):
    W = 1280
    hdr = festive_header(age, tour, W)
    sections = [("ЛУЧШИЕ БОМБАРДИРЫ", rec["scorers"], "гол."), ("ЛУЧШИЕ ПО ПЕРЕДАЧАМ", rec["assists"], "пер."),
                ("ВРАТАРИ «НА НОЛЬ»", rec["zeros"], "матч.")]
    sections = [s for s in sections if s[1]]
    facts = [(name, val) for name, val in (("Крупнейшая победа", rec["biggest"]), ("Самая результативная игра", rec["richest"]),
                                            ("Лучшая серия побед", rec["streak"])) if val]
    rh, sh = 78 * S, 58 * S
    H = hdr.height + 84 * S + sum(sh + rh * len(s[1]) for s in sections) + (sh + rh * len(facts) if facts else 0) + 60 * S
    img = Image.new("RGBA", (W * S, H), BG + (255,))
    img.paste(hdr, (0, 0))
    d = ImageDraw.Draw(img)
    y = hdr.height
    d.text((36 * S, y + 40 * S), f"РЕКОРДЫ {YEAR}", font=_f(34), fill=AMBER, anchor="lm")
    tw = d.textlength(f"РЕКОРДЫ {YEAR}", font=_f(34))
    _dots(d, SNOWFLAKE, 36 * S + tw + 18 * S, y + 26 * S, 4 * S, lambda r, c: (210, 230, 255))
    d.text((W * S - 36 * S, y + 40 * S), period_text, font=_f(22, False), fill=MUTED, anchor="rm")
    y += 84 * S
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lit = []
    for title, rows, unit in sections:
        d.text((36 * S, y + sh // 2), title, font=_f(22), fill=MUTED, anchor="lm")
        y += sh
        for i, (name, team, k) in enumerate(rows):
            d.rounded_rectangle([20 * S, y + 4 * S, W * S - 20 * S, y + rh - 4 * S], radius=12 * S,
                                fill=PANEL if i % 2 == 0 else PANEL2, outline=AMBER if i == 0 else EDGE, width=(3 if i == 0 else 1) * S)
            mid = y + rh // 2
            _led(d, str(i + 1), 58 * S, mid - 3.5 * 4 * S, 4 * S, AMBER)
            d.text((110 * S, mid), name.upper(), font=_f(26), fill=TEXT, anchor="lm")
            nw = d.textlength(name.upper(), font=_f(26))
            d.text((110 * S + nw + 22 * S, mid), team, font=_f(22, False), fill=MUTED, anchor="lm")
            val, cell = str(k), 6 * S
            vx = (W - 140) * S - (len(val) * cell * 6.2 - cell * 1.2) / 2
            _led(gd, val, vx, mid - 3.5 * cell, cell, (255, 160, 0, 170))
            lit.append((val, vx, mid - 3.5 * cell, cell))
            d.text(((W - 60) * S, mid), unit, font=_f(18, False), fill=MUTED, anchor="mm")
            y += rh
    if facts:
        d.text((36 * S, y + sh // 2), "РЕКОРДЫ МАТЧЕЙ", font=_f(22), fill=MUTED, anchor="lm")
        y += sh
        for i, (name, val) in enumerate(facts):
            d.rounded_rectangle([20 * S, y + 4 * S, W * S - 20 * S, y + rh - 4 * S], radius=12 * S,
                                fill=PANEL if i % 2 == 0 else PANEL2, outline=EDGE, width=S)
            mid = y + rh // 2
            d.text((44 * S, mid), name, font=_f(22, False), fill=MUTED, anchor="lm")
            d.text(((W - 44) * S, mid), val.upper(), font=_f(24), fill=TEXT, anchor="rm")
            y += rh
    d.text((36 * S, H - 30 * S), "Первенство СПб и Кубок Федерации · данные протоколов spb.fhr.ru",
           font=_f(18, False), fill=MUTED, anchor="lm")
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(8 * S)))
    d = ImageDraw.Draw(img)
    for val, vx, vy, cell in lit:
        _led(d, val, vx, vy, cell, AMBER)
    img.convert("RGB").resize((W, H // S), Image.LANCZOS).save(out)
    return out


def send_albums(paths, caption):
    for start in range(0, len(paths), 10):
        chunk = paths[start:start + 10]
        media = [dict({"type": "photo", "media": f"attach://p{i}"},
                      **({"caption": caption, "parse_mode": "HTML"} if start == 0 and i == 0 else {}))
                 for i in range(len(chunk))]
        files = {f"p{i}": open(p, "rb") for i, p in enumerate(chunk)}
        try:
            if len(chunk) == 1:
                r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                                  data={"chat_id": ADMIN_ID, "caption": caption if start == 0 else ""},
                                  files={"photo": files["p0"]}, timeout=60).json()
            else:
                r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup",
                                  data={"chat_id": ADMIN_ID, "media": json.dumps(media, ensure_ascii=False)},
                                  files=files, timeout=120).json()
        finally:
            for f in files.values():
                f.close()
        if not r.get("ok"):
            raise RuntimeError(r)


# ----------------------------------------------------------------- поздравление в полночь
def totals(stats):
    t = {"games": 0, "goals": 0, "pim": 0}
    for columns in stats.values():
        for col in columns.values():
            for k in t:
                t[k] += col[k]
    return t


def _num(n):
    return f"{n:,}".replace(",", " ")


def greeting_video(tot, out_mp4, fps=12):
    """Ролик-поздравление: отсчёт 00:10…00:01 на табло, затем «2027» с салютом."""
    import math
    import random
    import imageio.v2 as imageio
    import numpy
    W, Hh = 1280, 720
    nxt = str(YEAR + 1)
    sky = Image.new("RGB", (W, Hh))
    sd = ImageDraw.Draw(sky)
    for y in range(Hh):
        t = y / Hh
        sd.line([(0, y), (W, y)], fill=(int(8 + 12 * t), int(12 + 18 * t), int(28 + 30 * t)))
    rnd = random.Random(31)
    # вспышки салюта — вокруг табло (x 190–1090, y 150–470), не поверх цифр
    spots = [(95, 250, 85), (1185, 260, 85), (110, 560, 80), (1170, 560, 80), (330, 82, 60), (950, 80, 60), (640, 640, 0)]
    bursts = [(x, y, rnd.choice(BULBS_GREET), rnd.randrange(0, 24), r) for x, y, r in spots if r]
    frames = [("count", s, f) for s in range(10, 0, -1) for f in range(6)] + [("year", 0, f) for f in range(48)]

    def led_text(d, text, cx, y, cell, color):
        w = sum(cell * (6.2 if ch != ":" else 4.4) for ch in text) - cell * 1.2
        x = cx - w / 2
        for ch in text:
            for r, row in enumerate(tb.GLYPHS[ch]):
                for c, bit in enumerate(row):
                    if bit == "1":
                        d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * 0.84, y + r * cell + cell * 0.84], fill=color)
            x += cell * (6.2 if ch != ":" else 4.4)

    with imageio.get_writer(out_mp4, fps=fps, codec="libx264", quality=8, macro_block_size=1, pixelformat="yuv420p") as wr:
        for i, (kind, sec, f) in enumerate(frames):
            img = sky.copy().convert("RGBA")
            img.alpha_composite(festive.falling_snow(W, Hh, i % 48, 48, seed=5, count=260))
            img.alpha_composite(festive.garland_layer(W, 60, W / 1200, i % 48, 48))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([190, 150, 1090, 470], radius=26, fill=(20, 24, 34), outline=(52, 60, 78), width=4)
            glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
            gd = ImageDraw.Draw(glow)
            if kind == "count":
                d.text((W / 2, 196), "ДО НОВОГО ГОДА", font=_f(17), fill=(150, 160, 180), anchor="mm")
                text, color = f"00:{sec:02d}", (255, 196, 40)
            else:
                text, color = nxt, (255, 210, 60)
                for bx, by, col, delay, radius in bursts:              # салют
                    t = (f - delay % 24) / 24
                    if 0 <= t <= 1:
                        for a in range(0, 360, 18):
                            for k in (0.4, 0.7, 1.0):
                                rr = radius * t * k
                                x, y = bx + math.cos(math.radians(a)) * rr, by + math.sin(math.radians(a)) * rr
                                s, alpha = 9 * (1 - t * 0.5), int(255 * (1 - t))
                                gd.ellipse([x - s, y - s, x + s, y + s], fill=col + (alpha,))
                                d.ellipse([x - s / 2, y - s / 2, x + s / 2, y + s / 2], fill=col + (alpha,))
            led_text(gd, text, W / 2, 228, 24, color + (255,))
            img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(14)))
            d = ImageDraw.Draw(img)
            led_text(d, text, W / 2, 228, 24, color)
            if kind == "year":
                d.rounded_rectangle([W / 2 - 300, 500, W / 2 + 300, 572], radius=18, fill=(233, 30, 85))
                d.text((W / 2, 536), "С НОВЫМ ГОДОМ!", font=_f(22), fill=(255, 255, 255), anchor="mm")
            d.text((W / 2, 622), f"В {YEAR} году: {_num(tot['games'])} матчей · {_num(tot['goals'])} шайб",
                   font=_f(13, False), fill=(200, 210, 230), anchor="mm")
            d.text((W / 2, 668), "ВСЕССЫЛКИ.СПБ · детский хоккей Петербурга", font=_f(11, False), fill=(130, 140, 160), anchor="mm")
            wr.append_data(numpy.asarray(img.convert("RGB")))
    return out_mp4


BULBS_GREET = [(255, 80, 80), (80, 220, 120), (255, 200, 60), (90, 170, 255), (255, 120, 220), (255, 255, 255)]


def publish_preview(stats, games_of, tour_of, period, to_admin=True):
    """Пункт 4: по каждому году — альбом «итоги + рекорды» с праздничной подписью.
    to_admin=True — в личку (проверка); False — в темы годов рождения (31 декабря)."""
    try:
        from post_standings import TOPIC_IDS
    except Exception:
        TOPIC_IDS = {}
    sent = 0
    for age in sorted(stats):
        a = OUT_DIR / f"{age}.png"
        b = OUT_DIR / f"{age}_records.png"
        if not (a.exists() and b.exists()):
            continue
        caption = (f"🎄 <b>Итоги {YEAR} · {age} г.р.</b>\n"
                   f"Матчи, шайбы, штрафы, лучшие бомбардиры, ассистенты и вратари года.\n"
                   f"С наступающим Новым годом! ❄️")
        topic = TOPIC_IDS.get(age)
        if not to_admin and not topic:
            continue
        media = [{"type": "photo", "media": "attach://a", "caption": caption, "parse_mode": "HTML"},
                 {"type": "photo", "media": "attach://b"}]
        data = {"chat_id": ADMIN_ID if to_admin else TG_CHAT_ID, "media": json.dumps(media, ensure_ascii=False)}
        if not to_admin:
            data["message_thread_id"] = topic
        with open(a, "rb") as fa, open(b, "rb") as fb:
            r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup", data=data,
                              files={"a": fa, "b": fb}, timeout=120).json()
        sent += bool(r.get("ok"))
        time.sleep(2)
    return sent


def show_stages():
    """Какие группы и этапы найдены по каждому году и сколько в них сыгранных матчей 2026 года."""
    session = spb_fhr_client.create_session()
    for season, table in (("2025/26", PREV_SEASON), ("2026/27", CUR_SEASON)):
        print(f"\n=== сезон {season}")
        for tid, slug, tour, years in table:
            for age, year_id in years.items():
                groups = prev_groups(session, slug, year_id) if season == "2025/26" else cur_groups(session, slug, year_id)
                parts = []
                for label, gid in groups:
                    rows = ps._spb_calendar_rows(session, tid, slug, year_id, gid)
                    n = sum(1 for g in rows if g.get("score") and g["date"].endswith(str(YEAR)))
                    parts.append(f"{label}: {n}")
                print(f"  {age} {tour[:10]:10} " + (" | ".join(parts) if parts else "этапы не найдены"))


def main():
    if "--stages" in sys.argv:
        show_stages()
        return
    if "--monthly" in sys.argv and (datetime.now() + timedelta(days=1)).day != 1:
        return                                   # не последний день месяца
    date_to = datetime.now()
    if "--to" in sys.argv:
        date_to = datetime.strptime(sys.argv[sys.argv.index("--to") + 1], "%d.%m.%Y")
    date_to = date_to.replace(hour=23, minute=59)
    print(f"Итоги {YEAR}: 01.01–{date_to:%d.%m.%Y}. Собираю данные spb.fhr.ru…")
    stats, tour_of, games_of = collect(date_to)
    OUT_DIR.mkdir(exist_ok=True)
    period = f"01.01 – {date_to:%d.%m.%Y}"
    paths = [render(age, stats[age], tour_of.get(age), period, OUT_DIR / f"{age}.png")
             for age in sorted(stats)]
    print(f"Картинок: {len(paths)} в {OUT_DIR}")
    rec_paths = [render_records(age, records(games_of[age]), tour_of.get(age), period, OUT_DIR / f"{age}_records.png")
                 for age in sorted(games_of)]
    print(f"Картинок рекордов: {len(rec_paths)}")
    if "--preview" in sys.argv:
        return
    if "--publish-test" in sys.argv:                 # пункты 4 и 6 — проверка в личке
        n = publish_preview(stats, games_of, tour_of, period, to_admin=True)
        mp4 = greeting_video(totals(stats), str(OUT_DIR / "greeting.mp4"))
        with open(mp4, "rb") as fh:
            requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendAnimation", files={"animation": fh},
                          data={"chat_id": ADMIN_ID, "caption": f"🎆 С Новым {YEAR + 1} годом! (так поздравление выйдет в полночь)"},
                          timeout=120)
        print(f"В личку: {n} альбомов «итоги + рекорды» по годам и поздравление")
        return
    send_albums(paths, f"📊 <b>Итоги {YEAR} по годам рождения</b>\nПервенство СПб и Кубок Федерации, {period}")
    send_albums(rec_paths, f"🏆 <b>Рекорды {YEAR} по годам рождения</b>\nБомбардиры, передачи, вратари «на ноль» и рекорды матчей, {period}")
    print("Отправлено в личку")


if __name__ == "__main__":
    main()
