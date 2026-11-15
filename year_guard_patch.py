#!/usr/bin/env python3
"""
cover_ocr.py: год рождения — обязательная проверка. Год с обложки
(«Контрольный матч 2012 г.р.») или из заголовка подставляется к названиям
команд с обложки, и матч другого года не принимается. Если год в заголовке
и на обложке разный — не привязываем.
Плюс уборка: ссылки, где год в заголовке видео не совпадает с годом матча.
Запуск (из ~/vk-bot):  python3 year_guard_patch.py
"""
import json, re, shutil, sys
from pathlib import Path
BASE = Path(__file__).parent
T = BASE / "cover_ocr.py"
ITEMS = [
('''    fx, why = _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt)
    if fx or not title or not lines:
        return fx, why
    year, hm, dates = year_in(lines), time_in(lines), dates_in(lines)''',
 '''    cover_year = year_in(lines or [])
    ty = re.search(r"(?<!\\d)(20(?:09|1\\d))(?!\\d)", title or "")
    title_year = ty.group(1) if ty else None
    if cover_year and title_year and cover_year != title_year:
        return None, f"год в заголовке {title_year}, на обложке {cover_year} — не привязываю"
    want = cover_year or title_year
    fx, why = _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt, want)
    if fx and want and fx.get("age") and fx["age"] != want[-2:]:
        fx, why = None, f"год {want}, а найденный матч — {fx['age']} г.р."
    if fx or not title or not lines:
        return fx, why
    year, hm, dates = cover_year, time_in(lines), dates_in(lines)'''),
('''def _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None):''',
 '''def _match_teams(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None, year=None):'''),
('''        fx, _ = match_title(cand + (f" {hm}" if hm else ""), dates, fixtures=fixtures,''',
 '''        if year and not re.search(r"(?<!\\d)20(?:09|1\\d)(?!\\d)", cand):
            cand = f"{cand} {year} г.р."           # год с обложки/заголовка — к командам
        fx, _ = match_title(cand + (f" {hm}" if hm else ""), dates, fixtures=fixtures,'''),
]
c = T.read_text(encoding="utf-8")
if "не привязываю" in c:
    print("cover_ocr.py: уже исправлено")
else:
    miss = [o[:50] for o, _ in ITEMS if c.count(o) != 1]
    if miss:
        sys.exit(f"cover_ocr.py: НЕ найдено {miss} — файл НЕ изменён")
    shutil.copy(T, T.with_name("cover_ocr.py.bak_year"))
    for o, n in ITEMS:
        c = c.replace(o, n, 1)
    T.write_text(c, encoding="utf-8")
    print("cover_ocr.py: год рождения проверяется обязательно")

YR = re.compile(r"(?<!\d)20(09|1\d)(?![\d-])")   # «2011-12 г.р.» — два года, не трогаем
for name, seen_name in (("video_index.json", None), ("rutube_index.json", "rutube_seen.json"),
                        ("youtube_index.json", "youtube_seen.json")):
    p = BASE / name
    if not p.exists():
        continue
    idx = json.loads(p.read_text(encoding="utf-8"))
    bad = []
    for k, v in idx.items():
        if not isinstance(v, dict):
            continue
        ages = set(YR.findall(v.get("title", "")))
        m = re.search(r"::(\d{2})$", k)
        if m and len(ages) == 1 and m.group(1) not in ages:
            bad.append(k)
    for k in bad:
        print(f"{name}: убрана ссылка с другим годом: {k} ← {idx[k].get('title')}")
        url = idx[k].get("url") or idx[k].get("video_url", "")
        del idx[k]
        if seen_name:
            sp = BASE / seen_name
            seen = json.loads(sp.read_text(encoding="utf-8"))
            for vid in [vid for vid in seen if vid in url]:
                del seen[vid]
            sp.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")
    if bad:
        p.write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
