#!/usr/bin/env python3
"""
Пост дня на ЗАВТРАШНИЕ игры публикуется только вечером накануне, после 22:00.
Игры сегодня и прошедшие — публикуются сразу, как раньше.

Запуск (из ~/vk-bot):  python3 eve_publish_patch.py
Резервная копия: post_schedule.py.bak_eve
"""
import re
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"
PATTERN = re.compile(r"^(?P<ind>[ \t]+)if days_until > 1:\n(?P=ind)    continue\n", re.M)

content = TARGET.read_text(encoding="utf-8")
if "PUBLISH_EVE_HOUR" in content:
    print("Уже применено.")
    sys.exit(0)

found = PATTERN.findall(content)
if len(found) != 2:
    print(f"ВНИМАНИЕ: ожидалось 2 места с правилом публикации, найдено {len(found)}. Файл НЕ изменён.")
    sys.exit(1)


def repl(m):
    ind = m.group("ind")
    return (f"{ind}if days_until > 1:\n"
            f"{ind}    continue\n"
            f"{ind}# Пост на ЗАВТРАШНИЕ игры — только вечером накануне, после\n"
            f"{ind}# PUBLISH_EVE_HOUR (игры сегодня/прошедшие публикуются сразу).\n"
            f"{ind}if days_until == 1 and datetime.now().hour < PUBLISH_EVE_HOUR:\n"
            f"{ind}    continue\n")


content = PATTERN.sub(repl, content)
anchor = 'OFFICIAL_MATCHES_FILE = Path(__file__).parent / "official_matches.json"\n'
if content.count(anchor) != 1:
    print("ВНИМАНИЕ: не найдено место для настройки часа. Файл НЕ изменён.")
    sys.exit(1)
content = content.replace(anchor, anchor + "PUBLISH_EVE_HOUR = 22  # пост на завтра — не раньше этого часа накануне\n")

shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_eve"))
TARGET.write_text(content, encoding="utf-8")
print("Готово: посты на завтра будут выходить после 22:00 (резервная копия: post_schedule.py.bak_eve)")
