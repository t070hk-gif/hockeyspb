#!/usr/bin/env python3
"""
Проверка правок (EDIT-CHECK) в vk_to_tg_hockey_bot.py больше не путает
разные видео с одинаковым номером из РАЗНЫХ групп VK и не считает правкой
заглушку «Видео недоступно».

Запуск (из ~/vk-bot):  python3 editcheck_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_editcheck
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

ANCHOR = '''            if (current_title == snapshot["title"]
                    and current_description == snapshot["description"]):
                continue  # без изменений
'''
ADD = '''
            # Номер видео уникален только ВНУТРИ группы VK, а снимок хранится
            # по голому номеру. Без этой проверки ролик одной группы
            # сравнивался со снимком ролика ДРУГОЙ группы с тем же номером,
            # и бот "видел" правку, которой не было (матчи переезжали между
            # постами туда-обратно каждый цикл).
            if current_title.strip().lower() in ("видео недоступно", "video unavailable",
                                                  "video is unavailable"):
                continue  # заглушка VK для скрытого/удалённого ролика — не правка
            owner_map = state.setdefault("_sent_owner", {})
            snap_owner = owner_map.get(vid_str)
            if snap_owner is None:
                gk = snapshot.get("group_key")
                entry = ((day_posts.get(gk) or {}).get("matches") or {}).get(vid_str) if gk else None
                m_owner = re.search(r"video(-?\\d+)_", (entry or {}).get("video_url", ""))
                if m_owner:
                    snap_owner = int(m_owner.group(1))
                    owner_map[vid_str] = snap_owner
            if snap_owner != video["owner_id"]:
                continue  # снимок от другого ролика (другая группа) или владелец неизвестен
'''

content = TARGET.read_text(encoding="utf-8")
if '"_sent_owner"' in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(ANCHOR) != 1:
    print("ВНИМАНИЕ: место не найдено однозначно, файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_editcheck"))
TARGET.write_text(content.replace(ANCHOR, ANCHOR + ADD), encoding="utf-8")
print("Проверка правок исправлена (резервная копия: vk_to_tg_hockey_bot.py.bak_editcheck)")
