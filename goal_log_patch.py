#!/usr/bin/env python3
"""
Журнал голов: когда бот впервые увидел каждый гол на сайте (live_goals_log.jsonl),
и отчёт по задержке:  python3 goals_delay.py [ДД.ММ.ГГГГ]
Запуск (из ~/vk-bot):  python3 goal_log_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent
T = BASE / "post_schedule.py"
ITEMS = [
('''        live_score_line_text = None                # live-счёт — на баннере, не в тексте
''',
 '''        if is_live_now and periods_breakdown and spb_match:
            _log_live_goals(spb_match, m, periods_breakdown, date_label)
        live_score_line_text = None                # live-счёт — на баннере, не в тексте
'''),
('''_LIVE_SCORES = {}        # ключ матча -> live-счёт (для баннера)
''',
 '''_LIVE_SCORES = {}        # ключ матча -> live-счёт (для баннера)
GOALS_LOG_FILE = Path(__file__).parent / "live_goals_log.jsonl"
_GOALS_SEEN = None


def _log_live_goals(spb_match, m, breakdown, date_label):
    """Записывает время, когда бот впервые увидел каждый гол (для проверки задержки)."""
    global _GOALS_SEEN
    if _GOALS_SEEN is None:
        _GOALS_SEEN = set()
        try:
            for line in GOALS_LOG_FILE.read_text(encoding="utf-8").splitlines()[-3000:]:
                _GOALS_SEEN.add(json.loads(line)["id"])
        except Exception:
            pass
    new = []
    for period in breakdown:
        label = period.get("label") or f"{period.get('period_number', '?')}-й период"
        for tg in period.get("team_goals", []):
            for g in tg.get("goals", []):
                gid = f"{spb_match['game_id']}|{label}|{g.get('minute')}|{g.get('number')}"
                if gid in _GOALS_SEEN:
                    continue
                _GOALS_SEEN.add(gid)
                new.append({"id": gid, "seen": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                            "date": plain_date(date_label), "start": m.get("time"),
                            "match": f"{m['team1']} — {m['team2']}", "team": tg.get("name"),
                            "period": label, "minute": g.get("minute"),
                            "player": f"{g.get('number')}.{g.get('player')}",
                            "score": period.get("score")})
    if new:
        with open(GOALS_LOG_FILE, "a", encoding="utf-8") as fh:
            for rec in new:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\\n")
'''),
]
c = T.read_text(encoding="utf-8")
if "def _log_live_goals" in c:
    print("post_schedule.py: уже исправлено"); sys.exit()
miss = [o.strip()[:60] for o, _ in ITEMS if c.count(o) != 1]
if miss:
    sys.exit(f"post_schedule.py: НЕ найдено {miss} — файл НЕ изменён")
shutil.copy(T, T.with_name("post_schedule.py.bak_goallog"))
for o, n in ITEMS:
    c = c.replace(o, n, 1)
T.write_text(c, encoding="utf-8")
print("post_schedule.py: бот записывает время появления каждого гола (live_goals_log.jsonl)")
