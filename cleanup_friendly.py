#!/usr/bin/env python3
"""
Чистка товарищеских постов от официальных матчей.

Проверяет КАЖДЫЙ матч во всех постах "Товарищеская игра" через
team_matcher: если это на самом деле официальный матч (дата поста ±3 дня),
он убирается из товарищеского поста, а его видео регистрируется для
официального поста (без перезаписи существующих ссылок). Опустевшие посты
удаляются.

    python3 cleanup_friendly.py           — только показать план
    python3 cleanup_friendly.py --apply   — выполнить

ВАЖНО: --apply запускать ТОЛЬКО при остановленном VK-боте, иначе бот
перезапишет state.json своей копией из памяти и изменения откатятся.
"""
import sys
from datetime import datetime, timedelta

sys.path.insert(0, ".")
import vk_to_tg_hockey_bot as bot
import team_matcher as tm


def nearby_dates(date_str, window=3):
    d = datetime.strptime(date_str, "%d.%m.%Y")
    result = [date_str]
    for k in range(1, window + 1):
        result.append((d + timedelta(days=k)).strftime("%d.%m.%Y"))
        result.append((d - timedelta(days=k)).strftime("%d.%m.%Y"))
    return result


def main():
    apply = "--apply" in sys.argv
    state = bot.load_state()
    day_posts = state.get("_friendly_day_posts", {})
    sent = state.get("_sent_videos", {})
    fixtures = tm.load_fixtures()
    aliases = tm.load_alias_groups()

    plan = []  # (group_key, vid, entry, fixture)
    for gk, post in day_posts.items():
        date = gk.split("_", 1)[1]
        for vid, e in post.get("matches", {}).items():
            title = f'{e.get("teams", "")} {e.get("age") or ""}'
            fx, _ = tm.match_title(title, nearby_dates(date), fixtures=fixtures, alias_groups=aliases)
            if fx:
                plan.append((gk, vid, e, fx))

    if not plan:
        print("Официальных матчей в товарищеских постах не найдено.")
        return

    print(f"Официальных матчей в товарищеских постах: {len(plan)}")
    for gk, vid, e, fx in plan:
        post = day_posts[gk]
        left = len(post["matches"]) - sum(1 for p in plan if p[0] == gk)
        action = "пост будет УДАЛЁН" if left == 0 else f"в посте останется {left}"
        print(f'  пост {gk} (сообщение {post["message_id"]}): {e.get("teams")} '
              f'→ официальный {fx["date"]} {fx["team1"]} — {fx["team2"]} (возр. {fx.get("age") or "?"}); {action}')

    if not apply:
        print("\nЭто только план. Для выполнения: остановите бота и запустите с --apply.")
        return

    touched = set()
    for gk, vid, e, fx in plan:
        written = bot.register_official_video(fx, e["video_url"], e.get("teams", ""))
        print(f'  видео {vid}: {"ссылка записана для официального поста" if written else "у официального матча ссылка уже была"}')
        day_posts[gk]["matches"].pop(vid, None)
        sent.pop(vid, None)
        touched.add(gk)

    for gk in touched:
        post = day_posts[gk]
        if post["matches"]:
            age, date = gk.split("_", 1)
            caption = bot.format_friendly_day_caption(date, post["matches"])
            banner = bot.get_friendly_banner_path(None if age == "unknown" else age)
            result = bot.edit_photo_message(post["message_id"], banner, caption)
            if result == "not_found":
                print(f"  пост {gk}: сообщение уже удалено в Telegram — убираем запись")
                del day_posts[gk]
            else:
                print(f"  пост {gk}: обновлён")
        else:
            bot.delete_telegram_message(post["message_id"])
            del day_posts[gk]
            print(f"  пост {gk}: удалён")

    bot.save_state(state)
    print("\nГотово. Теперь запустите бота.")


if __name__ == "__main__":
    main()
