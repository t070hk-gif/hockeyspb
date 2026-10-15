#!/usr/bin/env python3
"""
Ручной диалог прощает опечатки в названиях команд: если точного совпадения
с расписанием нет, ищется официальный матч этой даты с самыми похожими
названиями ("Севервсталь" -> "Северсталь"). Привязывает, только если
похожий матч один и явно ближе остальных.

Нужен уже применённый manual_video_patch.py.
Запуск (из ~/vk-bot):  python3 typo_tolerant_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_typo
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
OLD = '''    if fx:
        send_admin_message(_register_manual(fx, conv["video_url"], conv.get("title") or typed))
'''
NEW = '''    if not fx:
        fx = _closest_fixture(conv["date"], conv["team1"], conv["team2"], age)
    if fx:
        send_admin_message(_register_manual(fx, conv["video_url"], conv.get("title") or typed))
'''
ANCHOR = "def _register_manual("
ADD = '''def _closest_fixture(date, team1, team2, age=None):
    """Официальный матч даты с самыми похожими названиями команд (на случай
    опечатки). None, если похожего нет или выбор неоднозначен."""
    import difflib
    sk = team_matcher._skeleton
    a, b = sk(team1), sk(team2)
    scored = []
    for f in _get_fixtures().get(date, []):
        if age and f.get("age") and f["age"] != age:
            continue
        f1, f2 = sk(f["team1"]), sk(f["team2"])
        straight = min(difflib.SequenceMatcher(None, a, f1).ratio(), difflib.SequenceMatcher(None, b, f2).ratio())
        crossed = min(difflib.SequenceMatcher(None, a, f2).ratio(), difflib.SequenceMatcher(None, b, f1).ratio())
        scored.append((max(straight, crossed), f))
    scored.sort(key=lambda x: x[0], reverse=True)
    if scored and scored[0][0] >= 0.75 and (len(scored) == 1 or scored[1][0] < scored[0][0] - 0.1):
        return scored[0][1]
    return None


'''

content = TARGET.read_text(encoding="utf-8")
if "def _closest_fixture(" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(OLD) != 1 or content.count(ANCHOR) != 1:
    print("ВНИМАНИЕ: сначала примените manual_video_patch.py — файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_typo"))
TARGET.write_text(content.replace(OLD, NEW).replace(ANCHOR, ADD + ANCHOR, 1), encoding="utf-8")
print("Готово: ручной диалог прощает опечатки (резервная копия: vk_to_tg_hockey_bot.py.bak_typo)")
