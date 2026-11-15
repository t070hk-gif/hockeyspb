#!/usr/bin/env python3
"""
cover_ocr.py: если по обложке команды не читаются (логотипы вместо названий),
берём с обложки год («СРЕДИ КОМАНД 2015 Г.Р.»), дату («14.11.26») и время
(«15:15») и уточняем ими заголовок видео.
VK-бот и RUTUBE/YouTube передают заголовок в проверку обложки.
Запуск (из ~/vk-bot):  python3 hints_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent

CO = [
('''_DATE_RE = re.compile(r"(?<!\\d)(\\d{1,2})[./](\\d{1,2})[./](20\\d{2})(?!\\d)")''',
 '''_DATE_RE = re.compile(r"(?<!\\d)(\\d{1,2})[./](\\d{1,2})[./]((?:20)?\\d{2})(?!\\d)")
_YEAR_RE = re.compile(r"(?<!\\d)(20[01]\\d)\\s*(?:г\\.?\\s*р|г\\.р|года?\\s+рожд)", re.I)
_TIME_LINE_RE = re.compile(r"^\\W*([01]?\\d|2[0-3])[:.]([0-5]\\d)\\W*$")'''),
('''                s = f"{int(d):02d}.{int(m):02d}.{y}"''',
 '''                s = f"{int(d):02d}.{int(m):02d}.{y if len(y) == 4 else '20' + y}"'''),
('''def time_in(lines):
    for line in lines:
        if _DATE_RE.search(line):
            m = _TIME_RE.search(_DATE_RE.sub(" ", line))
            if m:
                return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None''',
 '''def time_in(lines):
    for line in lines:
        if _DATE_RE.search(line):
            m = _TIME_RE.search(_DATE_RE.sub(" ", line))
            if m:
                return f"{int(m.group(1)):02d}:{m.group(2)}"
    if dates_in(lines):                      # время отдельной строкой рядом с датой
        for line in lines:
            m = _TIME_LINE_RE.match(line)
            if m:
                return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def year_in(lines):
    """Год рождения с обложки («СРЕДИ КОМАНД 2015 Г.Р.»), если он один."""
    years = {m for line in lines for m in _YEAR_RE.findall(line)}
    return years.pop() if len(years) == 1 else None'''),
('''def match(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None):
    """(матч | None, пояснение). Матч — только если все варианты с обложки указывают на один."""''',
 '''def match(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None, title=None):
    """(матч | None, пояснение). Сначала команды с обложки; не вышло — заголовок + год/дата/время с обложки."""
    fx, why = _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt)
    if fx or not title or not lines:
        return fx, why
    year, hm, dates = year_in(lines), time_in(lines), dates_in(lines)
    if not (year or hm):
        return fx, why
    t = title
    if year and not re.search(r"(?<!\\d)20[01]\\d(?!\\d)", title):
        t += f" {year} г.р."
    if hm:
        t += f" {hm}"
    sd = start_dt
    if dates and hm:
        from datetime import datetime
        try:
            sd = datetime.strptime(f"{dates[0]} {hm}", "%d.%m.%Y %H:%M")
        except ValueError:
            pass
    fx2, _ = match_title(t, dates or list(fallback_dates or []), fixtures=fixtures,
                         alias_groups=alias_groups, start_dt=sd)
    if fx2:
        return fx2, "по заголовку и обложке: " + ", ".join(x for x in (year and f"{year} г.р.", hm) if x)
    return fx, why


def _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None):'''),
]
RT = [('''    fx, why = cover_ocr.match(lines, tm.match_title, fixtures, aliases, dates, datetime.fromtimestamp(ts))''',
       '''    fx, why = cover_ocr.match(lines, tm.match_title, fixtures, aliases, dates, datetime.fromtimestamp(ts), title=title)''')]
VK = [('''                              team_matcher.build_date_candidates(title, live_start, upload_ts), start_dt)''',
       '''                              team_matcher.build_date_candidates(title, live_start, upload_ts), start_dt,
                              title=title)''')]


def patch(name, items, marker):
    t = BASE / name
    if not t.exists():
        print(f"{name}: нет файла — пропускаю"); return
    c = t.read_text(encoding="utf-8")
    if marker in c:
        print(f"{name}: уже исправлено"); return
    miss = [o[:50] for o, _ in items if c.count(o) != 1]
    if miss:
        print(f"{name}: НЕ найдено {miss} — файл НЕ изменён"); return
    shutil.copy(t, t.with_name(name + ".bak_hints"))
    for o, n in items:
        c = c.replace(o, n, 1)
    t.write_text(c, encoding="utf-8")
    print(f"{name}: исправлено")


patch("cover_ocr.py", CO, "def year_in")
patch("rutube_watch.py", RT, "title=title)")
patch("vk_to_tg_hockey_bot.py", VK, "start_dt,\n                              title=title)")
