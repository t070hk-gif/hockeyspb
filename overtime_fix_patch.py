#!/usr/bin/env python3
"""
Исправление пометок ОТ/ПБ для Первенства:
  * spb.fhr.ru выводит блок периодов дважды — повтор отбрасывается;
  * строка буллитов на сайте есть всегда (часто "0:0"), поэтому решаем по
    счёту, а не по числу периодов: счёт в 4-м периоде — «ОТ»; 4-й "0:0",
    а в 5-м счёт — «ПБ»; иначе основное время.
  * сбрасывает запомненные пометки, чтобы бот пересчитал их по новому правилу.

Запуск (из ~/vk-bot):  python3 overtime_fix_patch.py
Резервная копия: post_schedule.py.bak_otfix
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

OLD = '''                periods = spb_fhr_client.fetch_match_live_details(session, gm["game_id"]).get("periods", [])
                if len(periods) < 3:
                    continue
                suffix = "ПБ" if len(periods) >= 5 else "ОТ" if len(periods) == 4 else ""
'''
NEW = '''                periods = spb_fhr_client.fetch_match_live_details(session, gm["game_id"]).get("periods", [])
                suffix = _overtime_suffix(periods)
                if suffix is None:
                    continue    # периоды ещё не внесены
'''

FUNC_ANCHOR = "def _mark_pervenstvo_overtime("
FUNC_ADD = '''def _overtime_suffix(periods):
    """«ОТ» / «ПБ» / "" по счёту периодов со spb.fhr.ru; None — данных нет.
    Сайт выводит блок периодов дважды, а строку буллитов показывает всегда
    (часто "0:0") — поэтому решаем по счёту, а не по числу периодов."""
    n = len(periods)
    if n >= 6 and n % 2 == 0 and periods[:n // 2] == periods[n // 2:]:
        periods = periods[:n // 2]
    if len(periods) < 3:
        return None
    scored = lambda p: p.replace(" ", "") not in ("0:0", ":", "")
    if len(periods) >= 4 and scored(periods[3]):
        return "ОТ"
    if len(periods) >= 5 and scored(periods[4]):
        return "ПБ"
    return ""


'''

content = TARGET.read_text(encoding="utf-8")
if "def _overtime_suffix(" in content:
    print("Уже применено.")
else:
    if content.count(OLD) != 1 or content.count(FUNC_ANCHOR) != 1:
        print("ВНИМАНИЕ: сначала примените overtime_patch.py — файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_otfix"))
    content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1).replace(OLD, NEW)
    TARGET.write_text(content, encoding="utf-8")
    print("Правило ОТ/ПБ исправлено (резервная копия: post_schedule.py.bak_otfix)")

cache = BASE / "pervenstvo_ot_cache.json"
if cache.exists():
    cache.unlink()
    print("Запомненные пометки сброшены — бот пересчитает их на ближайшем прогоне")
