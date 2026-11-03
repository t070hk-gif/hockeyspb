#!/usr/bin/env python3
"""
Раз в неделю: есть ли на junior.fhr.ru турнир с ПРЕДСТОЯЩИМИ матчами команд СПб,
которого бот ещё не ведёт (нет в JUNIOR_TOURNAMENTS). Если есть — сообщение в личку.
О каждом турнире сообщается один раз.      python3 junior_watch.py [--test]
"""
import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import spb_fhr_client as c
with redirect_stdout(io.StringIO()):
    import post_schedule as ps
from config import TG_BOT_TOKEN, ADMIN_ID

STATE = BASE / "junior_watch.json"
SPB = re.compile(r"Санкт-Петербург|СПб|\bСКА\b|Серебрян|Стрельна|Петергоф|Невский|Варяги|Колпино|Армия СКА|ГудГол|"
                 r"Легион|Шайба|Динамо[- ]Юниор|Динамо[- ]Форвард|Динамо[- ]Питер|Красная Машина Юниор", re.I)


def season():
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y}-{y + 1}"


def main():
    s = c.create_session_kubok_rossii()
    base = f"https://{c.KUBOK_ROSSII_DOMAIN}"
    r = s.get(f"{base}/fhr-ajax/SXRwcm9maXRcQXBwXEFqYXhcQWpheFRvdXJuYW1lbnRz/Z2V0VG91cm5hbWVudHNMaXN0/?season={season()}",
              timeout=25, headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/tournaments/"})
    try:
        text = json.dumps(r.json(), ensure_ascii=False).replace("\\/", "/")
    except Exception:
        text = r.text
    known = {t["slug"] for t in ps.JUNIOR_TOURNAMENTS if t["slug"]} | {c.KUBOK_ROSSII_TOURNAMENT_SLUG}
    try:
        notified = set(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        notified = set()
    today = datetime.now().date()
    news = []
    for slug in dict.fromkeys(re.findall(r"/tournaments/([a-z0-9-]+?-\d{6,})/", text)):
        if "-year-" in slug or slug in known or slug in notified:
            continue
        games, _ = c.fetch_junior_matches(s, slug, slug.rsplit("-", 1)[1])
        ahead = [g for g in games if SPB.search(f"{g['team1']} {g['team2']}")
                 and datetime.strptime(g["date"], "%d.%m.%Y").date() >= today]
        if ahead:
            ahead.sort(key=lambda g: datetime.strptime(g["date"], "%d.%m.%Y"))
            news.append((slug, len(ahead), ahead[0]))
    for slug, n, g in news:
        text = (f"🆕 На junior.fhr.ru турнир с играми команд СПб, который бот не ведёт:\n{base}/tournaments/{slug}/\n"
                f"Предстоит матчей с командами СПб: {n}, ближайший {g['date']}: {g['team1']} — {g['team2']}.\n"
                f"Чтобы подключить — добавьте его в JUNIOR_TOURNAMENTS (post_schedule.py).")
        print(text)
        if "--test" not in sys.argv:
            requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                          data={"chat_id": ADMIN_ID, "text": text}, timeout=20)
            notified.add(slug)
    STATE.write_text(json.dumps(sorted(notified)), encoding="utf-8")
    print(f"Проверено: новых турниров с командами СПб — {len(news)}")


if __name__ == "__main__":
    main()
