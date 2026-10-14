#!/usr/bin/env python3
"""
vk_to_tg_hockey_bot.py: видео считается привязанным, только если оно
записано под ключом НАСТОЯЩЕГО официального матча (верные дата, возраст,
состав). Видео, которое старая логика записала под неверным ключом (дата
загрузки анонса, опечатка в годе, общий ключ без возраста, не тот состав),
снова проверяется страховкой.

Запуск (из ~/vk-bot):  python3 placement_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_placement
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
START = "def _registered_video_ids() -> set:\n"
NEW_FUNC = '''def _registered_video_ids() -> set:
    """Полные id видео, привязанных к ОФИЦИАЛЬНЫМ матчам под правильным
    ключом. Запись под неверным ключом (старая логика: дата загрузки
    анонса, опечатка в годе, общий ключ без возраста при нескольких
    возрастах, не тот состав) привязкой не считается."""
    ages_by_key = {}
    for day in _get_fixtures().values():
        for f in day:
            ages_by_key.setdefault(f["key"], set()).add(f.get("age"))
    ids = set()
    for k, entry in load_video_index().items():
        parts = k.split("::")
        ages = ages_by_key.get("::".join(parts[:2]))
        if ages is None:
            continue                       # такого официального матча нет
        age = parts[2] if len(parts) > 2 else None
        if age is not None and age not in ages:
            continue                       # возраст не тот
        if age is None and len(ages) > 1:
            continue                       # общий ключ, а пара играет в нескольких возрастах
        m = re.search(r"video(-?\\d+)_(\\d+)", entry.get("video_url", ""))
        if m:
            ids.add(f"{m.group(1)}_{m.group(2)}")
    return ids


'''

content = TARGET.read_text(encoding="utf-8")
if "привязкой не считается" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(START) != 1:
    print("ВНИМАНИЕ: сначала примените sweep_patch.py — файл НЕ изменён")
    sys.exit(1)
i = content.index(START)
j = content.index("\ndef ", i + len(START))          # начало следующей функции
j = content.rindex("\n\n", i, j + 1) + 2 if content[j - 1] == "\n" else j + 1
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_placement"))
content = content[:i] + NEW_FUNC + content[j:].lstrip("\n")
TARGET.write_text(content, encoding="utf-8")
print("Проверка привязки исправлена (резервная копия: vk_to_tg_hockey_bot.py.bak_placement)")
