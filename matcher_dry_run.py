#!/usr/bin/env python3
"""
Прогон team_matcher по "застрявшим" видео (увидены ботом, но никуда не
пристроены).

    python3 matcher_dry_run.py           — только показать, ничего не менять
    python3 matcher_dry_run.py --apply   — зарегистрировать найденные в video_index

При --apply УЖЕ существующие ссылки никогда не перезаписываются (если для
матча видео уже есть — найденный дубль пропускается).
"""
import re
import sys
import time
from collections import Counter

sys.path.insert(0, ".")
import vk_to_tg_hockey_bot as bot
import team_matcher as tm


def main():
    apply = "--apply" in sys.argv
    if apply and not hasattr(bot, "register_official_video"):
        print("Режим --apply работает после этапа 3 (python3 stage3_patch.py).")
        return

    state = bot.load_state()
    video_index = bot.load_video_index()
    sent = state.get("_sent_videos", {})
    pending = state.get("_pending_friendly_matches", {})

    registered = set()
    for entry in video_index.values():
        m = re.search(r"video(-?\d+)_(\d+)", entry.get("video_url", ""))
        if m:
            registered.add(f"{m.group(1)}_{m.group(2)}")

    fixtures = tm.load_fixtures()
    aliases = tm.load_alias_groups()
    print(f"Официальных матчей в расписании: {sum(len(v) for v in fixtures.values())}")
    print()

    tokens = bot.load_tokens()
    access_token, tokens = bot.get_valid_access_token(tokens)

    matched, unmatched = [], []
    for group_id in bot.VK_GROUP_IDS:
        seen = {str(v) for v in state.get(str(group_id), [])}
        try:
            videos = bot.vk_get_group_videos(access_token, group_id, count=100) or []
        except Exception as e:
            print(f"Группа {group_id}: ошибка {e}")
            time.sleep(1.5)
            continue
        time.sleep(1.5)

        for v in videos:
            vid = str(v["id"])
            full_id = f"-{group_id}_{vid}"
            if vid not in seen or full_id in registered or vid in sent or vid in pending:
                continue
            title = v.get("title", "")
            dates = tm.build_date_candidates(title, v.get("live_start_time"), v.get("date"))
            result, reason = tm.match_title(title, dates, fixtures=fixtures, alias_groups=aliases)
            if result:
                matched.append((full_id, title, result))
            else:
                unmatched.append((full_id, title, reason))

    print(f"=== СОПОСТАВЛЕНО: {len(matched)} ===")
    added = skipped = 0
    for full_id, title, r in matched:
        line = f"  {r['date']} | {r['team1']} — {r['team2']} (возр. {r.get('age') or '?'})"
        if apply:
            url = f"https://vk.com/video{full_id}"
            written = bot.register_official_video(r, url, title)
            if written:
                line += f"  — ЗАРЕГИСТРИРОВАНО ({', '.join(k.split('::', 1)[1] for k in written)})"
                added += 1
            else:
                line += "  — все ключи уже заняты, пропущено"
                skipped += 1
        print(line)
        print(f"      ← {title[:90]}")

    if apply:
        print(f"\nЗарегистрировано: {added}, пропущено (все ключи уже заняты): {skipped}")

    print()
    print(f"=== НЕ СОПОСТАВЛЕНО: {len(unmatched)} ===")
    for reason, count in Counter(r for _, _, r in unmatched).most_common():
        print(f"  {count:4d}  {reason}")
    if "--verbose" in sys.argv:
        print()
        for full_id, title, reason in unmatched:
            if not reason.startswith("обзор"):
                print(f"  [{reason}] {title[:90]}")


if __name__ == "__main__":
    main()
