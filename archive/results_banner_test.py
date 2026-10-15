#!/usr/bin/env python3
"""
Пробный «баннер с результатами»: сверху баннер турнира, под ним строки
матчей дня — время, команды с логотипами, счёт с пометкой ОТ/ПБ,
победитель выделен. Присылает картинку с подписью администратору в ЛИЧКУ,
канал не трогает.

    python3 results_banner_test.py                         — Первенство 2011 А, 04.10.2026
    python3 results_banner_test.py 6575 2012 A 04.10.2026  — турнир, год, группа, дата
"""
import io
import re
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, ".")
import post_schedule as sched
import post_standings as st

ADMIN_ID = 1158946041
BASE = Path(__file__).parent
FONT_BOLD = BASE / "fonts" / "PT_Sans-Web-Bold.ttf"
FONT_REG = BASE / "fonts" / "PT_Sans-Web-Regular.ttf"

W, S = 1280, 2                      # итоговая ширина и коэффициент сглаживания
BG, ROW_ALT = (11, 18, 32), (18, 28, 48)
TEXT, MUTED, DIM = (255, 255, 255), (150, 164, 190), (95, 108, 132)
ACCENT = {"A": (255, 61, 90), "А": (255, 61, 90)}
ACCENT_DEFAULT = (0, 194, 255)
DAY_NAMES = {"Пн": "ПН", "Вт": "ВТ", "Ср": "СР", "Чт": "ЧТ", "Пт": "ПТ", "Сб": "СБ", "Вс": "ВС"}

_logo_cache = {}


def font(bold, size):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(str(path), size * S)
    except OSError:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size * S)


def logo_for(raw_name, size):
    display = st._fhspb_display_name(raw_name)
    if (display, size) in _logo_cache:
        return _logo_cache[(display, size)]
    img = None
    try:
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


def split_score(score):
    m = re.match(r"\s*(\d+)\s*:\s*(\d+)\s*(\S*)", score or "")
    return (int(m.group(1)), int(m.group(2)), m.group(3)) if m else None


def fit(draw, text, bold, size, max_w):
    """Шрифт, при котором текст влезает в max_w (уменьшаем при длинных названиях)."""
    while size > 14:
        f = font(bold, size)
        if draw.textlength(text, font=f) <= max_w:
            return f
        size -= 1
    return font(bold, size)


def render(banner_path, matches, date_label, group, title, out_path):
    accent = ACCENT.get(group, ACCENT_DEFAULT)
    if banner_path and Path(banner_path).exists():
        b = Image.open(banner_path).convert("RGB")
        header = b.resize((W * S, int(b.height * W * S / b.width)), Image.LANCZOS)
    else:
        header = Image.new("RGB", (W * S, 300 * S), BG)

    ROW, TOP, FOOT = 104 * S, 84 * S, 58 * S
    rows = sorted(matches, key=lambda m: m["time"])
    img = Image.new("RGB", (W * S, header.height + TOP + ROW * len(rows) + FOOT), BG)
    img.paste(header, (0, 0))
    d = ImageDraw.Draw(img)

    # заголовок блока результатов
    y = header.height
    d.rectangle([0, y, W * S, y + TOP], fill=BG)
    d.rectangle([0, y + TOP - 4 * S, W * S, y + TOP], fill=accent)
    dow, date = date_label.split()[0], date_label.split()[-1][:5]
    d.text((40 * S, y + TOP // 2 - 2 * S), f"РЕЗУЛЬТАТЫ  ·  {DAY_NAMES.get(dow, dow)} {date}",
           font=font(True, 34), fill=TEXT, anchor="lm")
    d.text((W * S - 40 * S, y + TOP // 2 - 2 * S), title, font=font(False, 24), fill=MUTED, anchor="rm")
    y += TOP

    cx = W * S // 2
    box_w, box_h, logo = 200 * S, 64 * S, 50 * S
    name_max = cx - box_w // 2 - 18 * S - logo - 16 * S - 118 * S
    for i, m in enumerate(rows):
        if i % 2:
            d.rectangle([0, y, W * S, y + ROW], fill=ROW_ALT)
        mid = y + ROW // 2
        d.text((32 * S, mid), m["time"], font=font(False, 24), fill=DIM, anchor="lm")

        sc = split_score(m.get("score"))
        t1, t2 = st._fhspb_display_name(m["team1"]), st._fhspb_display_name(m["team2"])
        win1 = sc and sc[0] > sc[1]
        win2 = sc and sc[1] > sc[0]

        # счёт
        d.rounded_rectangle([cx - box_w // 2, mid - box_h // 2, cx + box_w // 2, mid + box_h // 2],
                            radius=14 * S, fill=accent if sc else ROW_ALT, outline=None if sc else DIM, width=2 * S)
        if sc:
            shift = 16 * S if sc[2] else 0
            d.text((cx - shift, mid), f"{sc[0]} : {sc[1]}", font=font(True, 38), fill=BG, anchor="mm")
            if sc[2]:
                d.text((cx + box_w // 2 - 14 * S, mid + 2 * S), sc[2], font=font(True, 18), fill=BG, anchor="rm")
        else:
            d.text((cx, mid), "—  :  —", font=font(True, 30), fill=DIM, anchor="mm")

        # команда 1 (справа выровнена к счёту)
        lx = cx - box_w // 2 - 18 * S - logo
        l1 = logo_for(m["team1"], logo)
        if l1:
            img.paste(l1, (lx + (logo - l1.width) // 2, mid - l1.height // 2), l1)
        f1 = fit(d, t1, bool(win1), 29, name_max)
        d.text((lx - 16 * S, mid), t1, font=f1, fill=TEXT if (win1 or not sc) else MUTED, anchor="rm")

        # команда 2 (слева выровнена к счёту)
        rx = cx + box_w // 2 + 18 * S
        l2 = logo_for(m["team2"], logo)
        if l2:
            img.paste(l2, (rx + (logo - l2.width) // 2, mid - l2.height // 2), l2)
        f2 = fit(d, t2, bool(win2), 29, name_max)
        d.text((rx + logo + 16 * S, mid), t2, font=f2, fill=TEXT if (win2 or not sc) else MUTED, anchor="lm")
        y += ROW

    d.text((W * S - 40 * S, y + FOOT // 2), "fhspb.ru  ·  spb.fhr.ru", font=font(False, 20), fill=DIM, anchor="rm")
    img = img.resize((W, img.height // S), Image.LANCZOS)
    img.save(out_path, "PNG")
    return out_path


def caption_for(matches, date_label, age2):
    """Подпись в привычном виде: сыгранный матч — видео и протокол,
    несыгранный — видео и время. Счёт теперь на картинке."""
    video_index = sched.load_video_index()
    blocks = [date_label.upper()]
    for m in sorted(matches, key=lambda x: x["time"]):
        teams = f'{m["team1"]} - {m["team2"]}'
        url = sched.find_video_url(m["date"], m["team1"], m["team2"], video_index, age=age2)
        line = f'📺 <a href="{url}">{teams}</a>' if url else f"📺 {teams}"
        if split_score(m.get("score")):
            line += f'\n📋 <a href="{m["protocol_url"]}">Протокол матча</a>'
        else:
            line += f'\n🕐 {m["time"]}'
        blocks.append(line)
    blocks.append("<i>Источники: fhspb.ru, spb.fhr.ru</i>")
    return "\n\n".join(blocks)


def main():
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 6573
    age = sys.argv[2] if len(sys.argv) > 2 else "2011"
    group = sys.argv[3] if len(sys.argv) > 3 else "A"
    day = sys.argv[4] if len(sys.argv) > 4 else "04.10.2026"
    group = None if group in ("-", "") else group

    matches = [m for m in sched.parse_matches(sched.fetch_schedule_html(tid)) if m["date"].endswith(day)]
    if not matches:
        print("Матчей на эту дату нет"); return
    try:
        sched._mark_pervenstvo_overtime(age, group, matches)
    except Exception:
        pass

    suffix = ("_groupa" if group in ("A", "А") else "_groupb") if group else ""
    banner = sched.BANNERS_DIR / f"{age}{suffix}_champ.png"
    letter = {"A": "А", "B": "Б"}.get(group, group)
    title = f"Первенство СПб {age} г.р." + (f" · группа {letter}" if letter else "")
    out = render(banner, matches, matches[0]["date"], group, title, BASE / "results_banner_test.png")
    print("Картинка:", out)

    with open(out, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{sched.TG_BOT_TOKEN}/sendPhoto",
                          data={"chat_id": ADMIN_ID, "parse_mode": "HTML",
                                "caption": caption_for(matches, matches[0]["date"], age[-2:])},
                          files={"photo": f}, timeout=30).json()
    print("Отправлено в личку" if r.get("ok") else r)

if __name__ == "__main__":
    main()
