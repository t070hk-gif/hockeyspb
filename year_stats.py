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
from config import TG_BOT_TOKEN, ADMIN_ID
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
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(H.unescape(link)).query)
    raw = qs.get("params", [""])[0]
    try:
        dec = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode(errors="ignore")
    except Exception:
        return {}
    return dict(re.findall(r's:\d+:"([A-Z_]+)";s:\d+:"(\d*)"', dec))


def groups_from_html(page, year_id):
    """[(название, GROUP_ID)] из кнопок фильтра календаря для года year_id."""
    out = []
    for link, label in re.findall(r'data-ajax-link="([^"]+)"[^>]*>\s*([^<]{1,40}?)\s*<', page):
        ids = _decode(link)
        if ids.get("GROUP_ID") and ids.get("YEAR_ID", year_id) == year_id:
            if ids["GROUP_ID"] not in [g for _, g in out]:
                out.append((label.strip(), ids["GROUP_ID"]))
    return out


def prev_groups(session, slug, year_id):
    """Группы/этапы года в сезоне 2025/26: календарь турнира переключается на год фоновым запросом."""
    page = session.get(f"https://spb.fhr.ru/tournaments/{slug}/calendar/", timeout=25).text
    groups = groups_from_html(page, year_id)
    if groups:
        return groups
    for attrs, label in re.findall(r"<option([^>]*)>\s*([^<]{1,20}?)\s*</option>", page):
        val = re.search(r'value="(\d+)"', attrs)
        url = re.search(r'data-ajax="([^"]+)"', attrs)
        if val and url and val.group(1) == year_id:
            u = H.unescape(url.group(1))
            u = u if u.startswith("http") else "https://spb.fhr.ru" + u
            resp = session.get(u, timeout=25, headers={"X-Requested-With": "XMLHttpRequest",
                                                         "Referer": f"https://spb.fhr.ru/tournaments/{slug}/calendar/"})
            try:
                text = json.dumps(resp.json(), ensure_ascii=False).replace("\\/", "/").replace('\\"', '"')
            except Exception:
                text = resp.text
            return groups_from_html(text, year_id)
    return []


def cur_groups(session, slug, year_id):
    page = session.get(f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/", timeout=25).text
    groups = groups_from_html(page, year_id)
    if not groups:
        manual = getattr(ps, "SPB_MANUAL_GROUPS", {}).get(year_id) or []
        groups = [(f"Группа {i + 1}", g) for i, g in enumerate(manual)]
    return groups or [("Все", None)]


def game_details(session, game_id, cache):
    """Счёт по периодам и штрафные минуты матча (сыгранные запоминаются)."""
    if game_id in cache:
        return cache[game_id]
    html = session.get(f"https://spb.fhr.ru/games/{game_id}/", timeout=25,
                       headers={"Referer": "https://spb.fhr.ru/tournaments/"}).text
    periods = [f"{a}:{b}" for a, b in spb_fhr_client.PERIOD_SCORE_RE.findall(html)]
    try:
        pen = spb_protocol.summarize(html).get("penalty") or (0, 0)
    except Exception:
        pen = (0, 0)
    info = {"periods": periods, "pim": int(pen[0]) + int(pen[1])}
    cache[game_id] = info
    time.sleep(0.3)
    return info


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
                    n += 1
                tour_of[age] = tour if season == "cur" or age not in tour_of else tour_of[age]
                print(f"   {age} {season} {label}: {n} матчей")
                CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return stats, tour_of


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


def main():
    if "--monthly" in sys.argv and (datetime.now() + timedelta(days=1)).day != 1:
        return                                   # не последний день месяца
    date_to = datetime.now()
    if "--to" in sys.argv:
        date_to = datetime.strptime(sys.argv[sys.argv.index("--to") + 1], "%d.%m.%Y")
    date_to = date_to.replace(hour=23, minute=59)
    print(f"Итоги {YEAR}: 01.01–{date_to:%d.%m.%Y}. Собираю данные spb.fhr.ru…")
    stats, tour_of = collect(date_to)
    OUT_DIR.mkdir(exist_ok=True)
    period = f"01.01 – {date_to:%d.%m.%Y}"
    paths = [render(age, stats[age], tour_of.get(age), period, OUT_DIR / f"{age}.png")
             for age in sorted(stats)]
    print(f"Картинок: {len(paths)} в {OUT_DIR}")
    if "--preview" in sys.argv:
        return
    send_albums(paths, f"📊 <b>Итоги {YEAR} по годам рождения</b>\nПервенство СПб и Кубок Федерации, {period}")
    print("Отправлено в личку")


if __name__ == "__main__":
    main()
