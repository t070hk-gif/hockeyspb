#!/usr/bin/env python3
"""
Ручной диалог: если официальный матч не найден, бот не записывает видео
«как есть» сразу, а просит прислать настоящие команды (в заголовке видео
бывают ошибки). Переспрашивает только если команды взяты из заголовка.
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
OLD = '''    else:
        video_index = load_video_index()
        key = build_match_key(conv["date"], conv["team1"], conv["team2"], age=age)
'''
NEW = '''    elif not conv.get("asked_again") and not conv.get("teams_typed"):
        # Возможно, в заголовке видео ошибка — спрашиваем настоящие команды.
        searched = f'{conv["team1"]} — {conv["team2"]}, {conv["date"]}' + (f", 20{age} г.р." if age else "")
        conv["asked_again"] = True
        conv["team1"] = conv["team2"] = None
        conv["step"] = "awaiting_teams"
        send_admin_message(f"⚠️ Матча «{searched}» в официальном расписании нет.\\n"
                           f"Если в названии видео ошибка, напишите настоящие команды через дефис, "
                           f"как в расписании (например: Северсталь - СКА Стрельна).\\n"
                           f"Дату и возраст оставлю те же. Или «отмена».")
        return True
    else:
        video_index = load_video_index()
        key = build_match_key(conv["date"], conv["team1"], conv["team2"], age=age)
'''
TEAMS_OLD = '''        conv["team1"], conv["team2"] = parts[0].strip(), parts[1].strip()
'''
TEAMS_NEW = '''        conv["team1"], conv["team2"] = parts[0].strip(), parts[1].strip()
        conv["teams_typed"] = True    # команды ввёл человек — переспрашивать не нужно
'''

content = TARGET.read_text(encoding="utf-8")
if 'conv.get("asked_again")' in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(OLD) != 1 or content.count(TEAMS_OLD) != 1:
    print("ВНИМАНИЕ: сначала примените manual_video_patch.py — файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_askagain"))
TARGET.write_text(content.replace(OLD, NEW).replace(TEAMS_OLD, TEAMS_NEW), encoding="utf-8")
print("Готово: при ненайденном матче бот переспрашивает команды")
