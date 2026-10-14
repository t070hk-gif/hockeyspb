#!/usr/bin/env python3
"""
Тестовый прогон: проверяет доступ к wall.get для ВСЕХ групп из VK_GROUP_IDS,
извлекает видео из постов/репостов и показывает, как распознаётся каждый
заголовок — БЕЗ отправки чего-либо в Telegram.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import importlib.util

spec = importlib.util.spec_from_file_location("bot", Path(__file__).parent / "vk_to_tg_hockey_bot.py")
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)


def main():
    tokens = bot.load_tokens()
    access_token, tokens = bot.get_valid_access_token(tokens)

    print(f"Проверка {len(bot.VK_GROUP_IDS)} групп...\n")
    print("=" * 70)

    total_videos = 0
    total_parsed = 0

    for group_id in bot.VK_GROUP_IDS:
        posts = bot.vk_get_wall_posts(access_token, group_id, count=20)

        if not posts:
            print(f"❌ Группа {group_id}: нет доступа или нет постов (проверьте вручную)")
            print("-" * 70)
            continue

        all_videos = []
        for post in posts:
            all_videos.extend(bot.extract_videos_from_post(post))

        unique_videos = {}
        for v in all_videos:
            unique_videos[v["id"]] = v

        print(f"✅ Группа {group_id}: {len(posts)} постов, {len(unique_videos)} уникальных видео")

        for video in list(unique_videos.values())[:5]:
            title = video.get("title", "")
            upload_ts = video.get("date")
            parsed = bot.parse_video_title(title, video.get("description", ""), upload_timestamp=upload_ts)
            total_videos += 1

            if parsed["teams"] or parsed["date"]:
                total_parsed += 1
                if parsed["teams"] and parsed["date"]:
                    status = "✅ РАСПОЗНАНО ПОЛНОСТЬЮ"
                elif parsed["teams"]:
                    status = "✅ КОМАНДЫ ЕСТЬ, дата не найдена"
                else:
                    status = "🟡 ДАТА ЕСТЬ, команды не выделены"
            else:
                status = "⚠️  НЕ распознано (уйдёт как есть)"

            print(f"   {status}")
            print(f"   Заголовок: {title}")
            if parsed["teams"]:
                print(f"   → Команды: {parsed['teams']}")
            if parsed["date"]:
                print(f"   → Дата: {parsed['date']}")
            print()

        print("-" * 70)

    print("=" * 70)
    print(f"\nИТОГО: проверено видео (образцы): {total_videos}, распознано: {total_parsed}")
    if total_videos:
        print(f"Процент распознавания: {100 * total_parsed / total_videos:.0f}%")


if __name__ == "__main__":
    main()
