#!/usr/bin/env python3
"""
Одноразовый скрипт: перебирает все записи в video_index.json, заново
разбирает сохранённый заголовок ("title") уже исправленным парсером
и, если правильный ключ отличается от старого, переносит запись под
новый ключ. Старые "испорченные" ключи удаляются.

Запуск (из папки vk-bot):
    python3 migrate_video_index.py
"""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("vkbot", "vk_to_tg_hockey_bot.py")
vkbot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vkbot)

INDEX_FILE = Path("video_index.json")


def main():
    if not INDEX_FILE.exists():
        print("video_index.json не найден.")
        return

    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    new_index = {}
    fixed_count = 0
    unchanged_count = 0
    unparseable_count = 0

    for old_key, entry in index.items():
        title = entry.get("title", "")
        parsed = vkbot.parse_video_title(title)

        if not parsed["teams"] or not parsed["date"]:
            print(f"[НЕ РАЗОБРАНО] {old_key!r} -- заголовок: {title!r}")
            new_index[old_key] = entry  # оставляем как есть, не теряем данные
            unparseable_count += 1
            continue

        team_parts = vkbot.TEAM_DASH_RE.split(parsed["teams"])
        if len(team_parts) != 2:
            print(f"[НЕ РАЗОБРАНО] {old_key!r} -- команды: {parsed['teams']!r}")
            new_index[old_key] = entry
            unparseable_count += 1
            continue

        team1, team2 = team_parts[0].strip(), team_parts[1].strip()
        new_key = vkbot.build_match_key(parsed["date"], team1, team2)

        if new_key != old_key:
            print(f"[ИСПРАВЛЕНО] {old_key!r}\n         -> {new_key!r}")
            fixed_count += 1
        else:
            unchanged_count += 1

        new_index[new_key] = entry

    INDEX_FILE.write_text(json.dumps(new_index, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"Итого: исправлено {fixed_count}, без изменений {unchanged_count}, "
          f"не удалось разобрать {unparseable_count}")


if __name__ == "__main__":
    main()
