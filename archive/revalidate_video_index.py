#!/usr/bin/env python3
"""
Перепроверяет КАЖДУЮ запись в video_index.json заново через актуальный VK
API (с описанием и live_start_time) — исправляет даты у видео, которые
были зарегистрированы ДО того, как появилось извлечение даты из описания
и live_start_time (тогда использовался менее точный fallback — дата
создания объекта видео в VK, которая может отличаться от реальной даты
игры на несколько дней).

Запуск (из папки vk-bot):
    python3 revalidate_video_index.py
"""

import importlib.util
import json
import re
import time
from pathlib import Path

import requests

spec = importlib.util.spec_from_file_location("vkbot", "vk_to_tg_hockey_bot.py")
vkbot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vkbot)

INDEX_FILE = Path("video_index.json")
VIDEO_URL_RE = re.compile(r'video(-?\d+)_(\d+)')


def fetch_video_details(access_token, owner_id, video_id):
    resp = requests.get(
        "https://api.vk.com/method/video.get",
        params={
            "videos": f"{owner_id}_{video_id}",
            "access_token": access_token,
            "v": vkbot.VK_API_VERSION,
        },
        timeout=15,
    )
    data = resp.json()
    items = data.get("response", {}).get("items", [])
    return items[0] if items else None


def main():
    if not INDEX_FILE.exists():
        print("video_index.json не найден.")
        return

    tokens = vkbot.load_tokens()
    access_token, tokens = vkbot.get_valid_access_token(tokens)

    index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    new_index = {}

    fixed_count = 0
    unchanged_count = 0
    not_found_count = 0
    error_count = 0

    total = len(index)
    for i, (old_key, entry) in enumerate(index.items(), 1):
        video_url = entry.get("video_url", "")
        m = VIDEO_URL_RE.search(video_url)
        if not m:
            new_index[old_key] = entry
            continue

        owner_id, video_id = m.groups()

        try:
            access_token, tokens = vkbot.get_valid_access_token(tokens)
            video = fetch_video_details(access_token, owner_id, video_id)
        except Exception as e:
            print(f"[ERROR] {video_url}: {e}")
            new_index[old_key] = entry
            error_count += 1
            continue

        if video is None:
            new_index[old_key] = entry
            not_found_count += 1
            continue

        title = video.get("title", "")
        description = video.get("description", "")
        upload_ts = video.get("date")
        live_start = video.get("live_start_time")

        parsed = vkbot.parse_video_title(title, description, upload_timestamp=upload_ts,
                                          live_start_time=live_start)

        if not parsed["teams"] or not parsed["date"]:
            new_index[old_key] = entry
            continue

        team_parts = vkbot.TEAM_DASH_RE.split(parsed["teams"])
        if len(team_parts) != 2:
            new_index[old_key] = entry
            continue

        team1, team2 = team_parts[0].strip(), team_parts[1].strip()
        new_key = vkbot.build_match_key(parsed["date"], team1, team2)

        if new_key != old_key:
            print(f"[ИСПРАВЛЕНО {i}/{total}] {old_key!r} -> {new_key!r}")
            fixed_count += 1
        else:
            unchanged_count += 1

        new_index[new_key] = entry

        time.sleep(0.3)  # не долбить VK API слишком часто

    INDEX_FILE.write_text(json.dumps(new_index, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"Итого: исправлено {fixed_count}, без изменений {unchanged_count}, "
          f"видео не найдено {not_found_count}, ошибок {error_count}")


if __name__ == "__main__":
    main()
