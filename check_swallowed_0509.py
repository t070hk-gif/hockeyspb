#!/usr/bin/env python3
"""
Диагностика: проверяет видео-каталог каждой группы напрямую, ищет
заголовки с упоминанием 05.09 (в разных форматах даты), и сверяет —
помечено ли уже это видео как "виденное" в state.json (то есть попало
ли оно под "проглатывание" базовой линии видео-каталога).

Запуск (из папки vk-bot):
    python3 check_swallowed_0509.py
"""

import importlib.util
import json
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location("vkbot", "vk_to_tg_hockey_bot.py")
vkbot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vkbot)

# Ловим "05.09", "5.09", "05/09", с годом или без — разные варианты написания
DATE_0509_RE = re.compile(r'\b0?5[./]0?9(?:[./]2?0?26)?\b')


def main():
    state = json.loads(Path("state.json").read_text(encoding="utf-8")) if Path("state.json").exists() else {}
    tokens = vkbot.load_tokens()
    access_token, tokens = vkbot.get_valid_access_token(tokens)

    total_found = 0
    total_swallowed = 0

    for group_id in vkbot.VK_GROUP_IDS:
        key = str(group_id)
        seen_ids = set(state.get(key, []))

        videos = vkbot.vk_get_group_videos(access_token, group_id)
        matches = [v for v in videos if DATE_0509_RE.search(v.get("title", ""))]

        if not matches:
            continue

        for v in matches:
            total_found += 1
            is_seen = v["id"] in seen_ids
            status = "ПРОГЛОЧЕНО (уже помечено виденным)" if is_seen else "не тронуто, будет обработано ботом само"
            if is_seen:
                total_swallowed += 1
            print(f"Группа {group_id} | id={v['id']} | {status}")
            print(f"  Заголовок: {v.get('title', '')}")
            print(f"  Ссылка: https://vk.com/video{v['owner_id']}_{v['id']}")
            print()

    print(f"=== ИТОГО: найдено с упоминанием 05.09 — {total_found}, "
          f"из них проглочено базовой линией — {total_swallowed} ===")


if __name__ == "__main__":
    main()
