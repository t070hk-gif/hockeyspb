#!/usr/bin/env python3
"""
Разовая замена картинок у опубликованных товарищеских постов на баннеры «Табло».
Подпись пересобирается той же функцией, что у бота; состояние бота не меняется.

    python3 refresh_friendly_banners.py            — показать, что будет обновлено (без изменений)
    python3 refresh_friendly_banners.py --apply    — заменить картинки (посты за 30 дней)
    python3 refresh_friendly_banners.py --apply --all   — все товарищеские посты
"""
import io
import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
with redirect_stdout(io.StringIO()):
    import vk_to_tg_hockey_bot as bot

apply_ = "--apply" in sys.argv
cutoff = None if "--all" in sys.argv else datetime.now() - timedelta(days=30)
posts = bot.load_state().get("_friendly_day_posts", {})
todo = []
for key, post in sorted(posts.items()):
    age, _, date_str = key.partition("_")
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y")
    except ValueError:
        d = None
    if cutoff and d and d < cutoff:
        continue
    if not post.get("message_id") or not post.get("matches"):
        continue
    todo.append((key, age, date_str, post))

print(f"Товарищеских постов к обновлению: {len(todo)}" + ("" if apply_ else "  (пробный прогон, ничего не меняю)"))
ok = 0
for key, age, date_str, post in todo:
    banner = bot.get_friendly_banner_path(None if age == "unknown" else age)
    if not apply_:
        print(f"  {key:28} → {banner.name}")
        continue
    caption = bot.format_friendly_day_caption(date_str, post["matches"])
    result = bot.edit_photo_message(post["message_id"], banner, caption)
    ok += result is True
    print(f"  {key:28} → {banner.name}: {'обновлён' if result is True else result}")
    time.sleep(3)                     # не чаще раза в 3 секунды — без претензий от Telegram
if apply_:
    print(f"Готово: обновлено {ok} из {len(todo)}")
