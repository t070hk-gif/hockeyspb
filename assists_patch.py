#!/usr/bin/env python3
"""
Передачи на баннере с результатами: голы для баннера берутся из протокола
матча (там есть ассистенты: «Демин 59' (Воробьев)»), если в протоколе их не
меньше, чем в обычных данных spb.fhr.ru. Сбрасывает запомненные протоколы,
чтобы бот перечитал их уже с передачами.

Нужен новый spb_protocol.py рядом.
Запуск (из ~/vk-bot):  python3 assists_patch.py
Резервная копия: post_schedule.py.bak_assists
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"
OLD = '''        if not g1 and not g2:
            g1, g2 = extra.pop("goals1", []), extra.pop("goals2", [])
'''
NEW = '''        p1, p2 = extra.get("goals1", []), extra.get("goals2", [])
        if (p1 or p2) and len(p1) + len(p2) >= len(g1) + len(g2):
            g1, g2 = p1, p2    # в протоколе есть передачи
'''

if "_ASSIST_RE" not in (BASE / "spb_protocol.py").read_text(encoding="utf-8"):
    print("ВНИМАНИЕ: сначала замените spb_protocol.py новой версией — файл НЕ изменён")
    sys.exit(1)
content = TARGET.read_text(encoding="utf-8")
if "в протоколе есть передачи" in content:
    print("Уже применено.")
else:
    if content.count(OLD) != 1:
        print("ВНИМАНИЕ: место не найдено — файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_assists"))
    TARGET.write_text(content.replace(OLD, NEW), encoding="utf-8")
    print("Передачи на баннере добавлены (резервная копия: post_schedule.py.bak_assists)")
cache = BASE / "spb_protocol_cache.json"
if cache.exists():
    cache.unlink()
    print("Запомненные протоколы сброшены — бот перечитает их с передачами")
