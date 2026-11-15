#!/usr/bin/env python3
"""
Отчёт: когда бот увидел каждый гол.  python3 goals_delay.py [ДД.ММ.ГГГГ]
«Бот увидел» — время, когда гол появился на spb.fhr.ru / junior.fhr.ru и попал в пост
(пост обновляется в тот же прогон, через несколько секунд).
Чтобы узнать полную задержку: откройте трансляцию на моменте гола и сравните
время на часах в этот момент со столбцом «бот увидел».
"""
import json, sys
from datetime import datetime
from pathlib import Path

day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%d.%m.%Y")
f = Path(__file__).parent / "live_goals_log.jsonl"
rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()] if f.exists() else []
rows = [r for r in rows if r.get("date") == day]
if not rows:
    sys.exit(f"За {day} голов в журнале нет (журнал пишется только во время live-матчей)")
cur = None
for r in sorted(rows, key=lambda r: (r["match"], r["seen"])):
    if r["match"] != cur:
        cur = r["match"]
        print(f"\n{cur}  (начало {r['start']})")
    seen = datetime.strptime(r["seen"], "%d.%m.%Y %H:%M:%S")
    try:
        start = datetime.strptime(f"{day} {r['start']}", "%d.%m.%Y %H:%M")
        since = f"{(seen - start).total_seconds() / 60:5.0f} мин от начала"
    except Exception:
        since = ""
    print(f"  бот увидел {seen:%H:%M:%S} · {since} · {r['period']}, {r['minute']}' · {r['player']} ({r['team']})")
