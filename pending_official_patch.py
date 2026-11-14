#!/usr/bin/env python3
"""
Отложенный «товарищеский» анонс перед публикацией в день игры ещё раз
сверяется с официальным расписанием (заголовок + обложка). Если это
официальный матч — видео привязывается к нему, а не публикуется в общий чат.
Запуск (из ~/vk-bot):  python3 pending_official_patch.py
"""
import shutil, sys
from pathlib import Path
T = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
OLD = '''        if is_official_match(parsed, official_keys):
            continue

        video_url = f"https://vk.com/video{entry['owner_id']}_{entry['id']}"
'''
NEW = '''        if is_official_match(parsed, official_keys):
            continue

        video_url = f"https://vk.com/video{entry['owner_id']}_{entry['id']}"
        try:       # день игры: ещё раз ищем официальный матч (заголовок + обложка)
            fx, why = _match_video_to_fixture(f"{title} {parsed['date']}", None, None,
                                              owner_id=entry["owner_id"],
                                              video_id=f"{entry['owner_id']}_{entry['id']}")
        except Exception as e:
            fx, why = None, str(e)
        if fx:
            written = register_official_video(fx, video_url, title)
            print(f"[OK] Отложенное видео {entry['id']} — официальный матч {fx['date']} "
                  f"{fx['team1']} — {fx['team2']} ({fx.get('age') or '?'}), {why}"
                  f"{'' if written else ', ссылка уже была'}: {title}")
            save_state(state)
            continue
'''
c = T.read_text(encoding="utf-8")
if "день игры: ещё раз ищем официальный матч" in c:
    print("vk_to_tg_hockey_bot.py: уже исправлено")
elif c.count(OLD) != 1:
    sys.exit("vk_to_tg_hockey_bot.py: место не найдено — файл НЕ изменён")
else:
    shutil.copy(T, T.with_name("vk_to_tg_hockey_bot.py.bak_pending"))
    T.write_text(c.replace(OLD, NEW, 1), encoding="utf-8")
    print("vk_to_tg_hockey_bot.py: отложенные анонсы перед публикацией сверяются с официальным расписанием")
