#!/usr/bin/env python3
"""
Поиск турниров Первенства СПб и Кубка Федерации на spb.fhr.ru по сезонам
(для итогов 2026 года нужны игры с января — это сезон 2025/26).
Ничего не меняет, только печатает.   Запуск (из ~/vk-bot):  python3 year_stats_discover.py
"""
import io
import json
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import spb_fhr_client
with redirect_stdout(io.StringIO()):
    import post_schedule as ps

LIST_AJAX = ("https://spb.fhr.ru/fhr-ajax/SXRwcm9maXRcQXBwXEFqYXhcQWpheFRvdXJuYW1lbnRz/"
             "Z2V0VG91cm5hbWVudHNMaXN0/?season={season}")
WANT = re.compile(r"/tournaments/((?:pervenstvo-spb|kubok-federatsii-spb)-(\d{6,}))/")
YEAR_LINK = re.compile(r'href="/tournaments/([a-z0-9-]+)-year-(\d+)/"[^>]*>(.*?)</a>', re.S)

s = spb_fhr_client.create_session()
for season in ("2025-2026", "2026-2027"):
    r = s.get(LIST_AJAX.format(season=season), timeout=25,
              headers={"X-Requested-With": "XMLHttpRequest", "Referer": "https://spb.fhr.ru/tournaments/"})
    try:
        data = r.json()
        text = json.dumps(data, ensure_ascii=False).replace("\\/", "/").replace('\\"', '"')
    except Exception:
        text = r.text
    tours = sorted(set(WANT.findall(text)))
    print(f"\n######## сезон {season}: турниров Первенства/Кубка Федерации — {len(tours)}")
    for slug, tid in tours:
        page = s.get(f"https://spb.fhr.ru/tournaments/{slug}/", timeout=25).text
        years = sorted({(re.sub(r"<[^>]+>|\s+", " ", lab).strip(), yid)
                        for yslug, yid, lab in YEAR_LINK.findall(page) if yslug == slug})
        print(f"\n== {slug}   TOURNAMENT_ID {tid}")
        for label, yid in years:
            if not re.search(r"20\d\d", label):
                continue
            try:
                gids = ps._spb_group_ids(s, slug, yid) or [None]
                rows = []
                for g in gids:
                    rows += ps._spb_calendar_rows(s, tid, slug, yid, g)
                dates = sorted({r["date"] for r in rows}, key=lambda d: d[6:] + d[3:5] + d[:2])
                played = sum(1 for r in rows if r.get("score"))
                span = f"{dates[0]} … {dates[-1]}" if dates else "календарь пуст"
                print(f"   {label[:12]:12} YEAR_ID {yid:9} групп {len(gids)}, игр {len(rows)} (сыграно {played})  {span}")
            except Exception as e:
                print(f"   {label[:12]:12} YEAR_ID {yid:9} ошибка: {e}")
