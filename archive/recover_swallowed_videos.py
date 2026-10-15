#!/usr/bin/env python3
"""
Проходит по видео-каталогу каждой группы, находит видео, которые уже
помечены "виденными" (проглочены базовой линией video.get), но при этом
успешно распознаются парсером (есть команды + дата) — и регистрирует их
в video_index.json напрямую, в обход обычного цикла бота.

Не переотправляет ничего в Telegram — только чинит индекс, которым
пользуется post_schedule.py.

Запуск (из папки vk-bot):
    python3 recover_swallowed_videos.py
"""

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location("vkbot", "vk_to_tg_hockey_bot.py")
vkbot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vkbot)


def main():
    state = json.loads(Path("state.json").read_text(encoding="utf-8")) if Path("state.json").exists() else {}
    tokens = vkbot.load_tokens()
    access_token, tokens = vkbot.get_valid_access_token(tokens)

    recovered = 0
    skipped_unparseable = 0
    skipped_not_swallowed = 0

    for group_id in vkbot.VK_GROUP_IDS:
        key = str(group_id)
        seen_ids = set(state.get(key, []))

        videos = vkbot.vk_get_group_videos(access_token, group_id)

        for v in videos:
            if v["id"] not in seen_ids:
                skipped_not_swallowed += 1
                continue  # это видео и так будет обработано ботом само

            title = v.get("title", "")
            description = v.get("description", "")
            upload_ts = v.get("date")
            parsed = vkbot.parse_video_title(title, description, upload_timestamp=upload_ts)

            if not parsed["teams"] or not parsed["date"]:
                skipped_unparseable += 1
                continue

            team_parts = vkbot.TEAM_DASH_RE.split(parsed["teams"])
            if len(team_parts) != 2:
                skipped_unparseable += 1
                continue

            vkbot.register_video_in_index(parsed, v)
            print(f"[ВОССТАНОВЛЕНО] {parsed['date']} :: {parsed['teams']} "
                  f"-> https://vk.com/video{v['owner_id']}_{v['id']}")
            recovered += 1

    print()
    print(f"=== ИТОГО: восстановлено {recovered}, "
          f"не распознано {skipped_unparseable}, "
          f"не было проглочено (и так будет обработано ботом) {skipped_not_swallowed} ===")


if __name__ == "__main__":
    main()
