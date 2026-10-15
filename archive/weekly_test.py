#!/usr/bin/env python3
"""
Тест недельного поста (неделя Вт–Пн, один пост на группу, баннер + компактная
подпись). Присылает пост администратору в ЛИЧКУ в двух вариантах:
  1) вся неделя открыта;
  2) прошедшие дни свёрнуты в раскрывающийся блок.
Канал и работающих ботов не трогает.

    python3 weekly_test.py                    — Первенство 2012, группа А (6575)
    python3 weekly_test.py 6576 2012 Б        — другая группа
    python3 weekly_test.py 6583 2016          — Кубок Федерации 2016 (без группы)
"""
import html
import re
import sys
from datetime import datetime, timedelta

import requests

sys.path.insert(0, ".")
import post_schedule as sched

ADMIN_ID = 1158946041
CAPTION_LIMIT = 1024
DAY_NAMES = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"]
_AGE_SUFFIX_RE = re.compile(r"\s(?:09|1[0-8])(?=(?:\s\d)?$)")


def week_bounds(day):
    """Неделя Вт–Пн, в которую попадает day."""
    start = day - timedelta(days=(day.weekday() - 1) % 7)
    return start, start + timedelta(days=6)


def match_date(m):
    return datetime.strptime(m["date"].split()[-1], "%d.%m.%Y").date()


def short_name(name):
    """'Варяги 12' -> 'Варяги', 'Красная Машина Юниор 12 2' -> 'Красная Машина Юниор 2'."""
    return _AGE_SUFFIX_RE.sub("", name).strip()


def visible_len(caption):
    """Длина так, как её считает Telegram: без HTML-тегов, в UTF-16."""
    text = html.unescape(re.sub(r"<[^>]+>", "", caption))
    return len(text.encode("utf-16-le")) // 2


def match_line(m, video_index, age2):
    t1, t2 = html.escape(short_name(m["team1"])), html.escape(short_name(m["team2"]))
    teams = f"{t1} — {t2}"
    video = sched.find_video_url(m["date"], m["team1"], m["team2"], video_index, age=age2)
    if video:
        teams = f'<a href="{video}">{teams}</a>'

    if m.get("score"):
        score = re.sub(r"(\d)([А-ЯA-Z])", r"\1 \2", m["score"].replace(" ", ""))
        score = html.escape(score)                      # "5:1ОТ" -> "5:1 ОТ"
        tail = f'<a href="{m["protocol_url"]}"><b>{score}</b></a>'
    elif sched.is_match_live(m["date"], m["time"]):
        tail = "🔴 LIVE"
    else:
        tail = ""
    return f"{m['time']}  {teams}  {tail}".rstrip()


def build_caption(matches, week_start, week_end, video_index, age2, collapse_past):
    today = datetime.now().date()
    by_day = {}
    for m in matches:
        by_day.setdefault(match_date(m), []).append(m)

    parts = [f"🏒 <b>Неделя {week_start:%d.%m} – {week_end:%d.%m}</b>"]
    for day in sorted(by_day):
        lines = [match_line(m, video_index, age2)
                 for m in sorted(by_day[day], key=lambda x: x["time"])]
        header = f"📅 <b>{DAY_NAMES[day.weekday()]} {day:%d.%m}</b>"
        body = "\n".join(lines)
        if collapse_past and day < today:
            parts.append(f"{header}\n<blockquote expandable>{body}</blockquote>")
        else:
            parts.append(f"{header}\n{body}")
    parts.append("<i>Источники: fhspb.ru, spb.fhr.ru</i>")
    return "\n\n".join(parts)


def banner_path(age, group):
    if group:
        suffix = "_groupa" if group.upper() in ("A", "А") else "_groupb"
        return sched.BANNERS_DIR / f"{age}{suffix}_champ.png"
    champ = sched.BANNERS_DIR / f"{age}_champ.png"
    cup = sched.BANNERS_DIR / f"{age}_cup.png"
    return cup if cup.exists() else champ


def send(banner, caption, label):
    with open(banner, "rb") as f:
        r = requests.post(
            f"https://api.telegram.org/bot{sched.TG_BOT_TOKEN}/sendPhoto",
            data={"chat_id": ADMIN_ID, "caption": caption, "parse_mode": "HTML"},
            files={"photo": f}, timeout=30,
        ).json()
    print(f"{label}: {'отправлено' if r.get('ok') else r}")


def main():
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else 6575
    age = sys.argv[2] if len(sys.argv) > 2 else "2012"
    group = sys.argv[3] if len(sys.argv) > 3 else ("A" if len(sys.argv) <= 1 else None)
    age2 = age[-2:]

    week_start, week_end = week_bounds(datetime.now().date())
    matches = [m for m in sched.parse_matches(sched.fetch_schedule_html(tid))
               if week_start <= match_date(m) <= week_end]
    print(f"Турнир {tid}, {age} {group or ''}: неделя {week_start:%d.%m}–{week_end:%d.%m}, матчей: {len(matches)}")
    if not matches:
        print("На этой неделе матчей нет — попробуйте другой турнир.")
        return

    banner = banner_path(age, group)
    if not banner.exists():
        print(f"Баннер не найден: {banner}")
        return

    video_index = sched.load_video_index()
    for collapse, label in ((False, "Вариант 1 (всё открыто)"), (True, "Вариант 2 (прошедшие свёрнуты)")):
        caption = build_caption(matches, week_start, week_end, video_index, age2, collapse)
        n = visible_len(caption)
        print(f"\n{label}: {n} из {CAPTION_LIMIT} символов{'  — НЕ ВЛЕЗАЕТ!' if n > CAPTION_LIMIT else ''}")
        print(caption)
        if n <= CAPTION_LIMIT:
            send(banner, f"[{label}]\n\n{caption}", label)


if __name__ == "__main__":
    main()
