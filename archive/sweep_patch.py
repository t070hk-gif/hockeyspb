#!/usr/bin/env python3
"""
Страховка в vk_to_tg_hockey_bot.py: видео, которое бот когда-то пометил
просмотренным, но так и не пристроил (не привязано к официальному матчу,
не опубликовано как товарищеское, не в очереди), каждый прогон
перепроверяется: сразу сопоставляется с расписанием, а если не вышло —
уходит в очередь нераспознанных (перепроверка раз в час, сводка в 21:00).
Смотрятся только видео не старше 10 дней, каждое — один раз.

Запуск (из ~/vk-bot):  python3 sweep_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_sweep
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

CALL_ANCHOR = "        new_videos = [v for vid, v in unique_videos.items() if vid not in seen_video_ids]\n"
CALL_ADD = '''        # Страховка: видео, помеченные просмотренными, но никуда не попавшие.
        _sweep_unplaced(state, group_id, unique_videos, seen_video_ids)

'''

FUNC_ANCHOR = "def check_groups_once("
FUNC_ADD = '''SWEEP_MAX_AGE_DAYS = 10


def _registered_video_ids() -> set:
    """Полные id ("-группа_номер") всех видео, уже привязанных к матчам."""
    ids = set()
    for entry in load_video_index().values():
        m = re.search(r"video(-?\\d+)_(\\d+)", entry.get("video_url", ""))
        if m:
            ids.add(f"{m.group(1)}_{m.group(2)}")
    return ids


def _sweep_unplaced(state: dict, group_id: int, unique_videos: dict, seen_ids: set) -> None:
    queue = state.setdefault("_unresolved_videos", {})
    sent = state.get("_sent_videos", {})
    pending = state.get("_pending_friendly_matches", {})
    swept = state.setdefault("_swept_videos", [])
    swept_set = set(swept)
    registered = None
    now = time.time()
    found = queued = 0

    for vid, v in unique_videos.items():
        full_id = f'{v["owner_id"]}_{vid}'
        if vid not in seen_ids or full_id in queue or full_id in swept_set:
            continue
        if str(vid) in sent or str(vid) in pending:
            continue
        ts = v.get("live_start_time") or v.get("date") or 0
        if now - ts > SWEEP_MAX_AGE_DAYS * 86400:
            continue
        if registered is None:
            registered = _registered_video_ids()
        if full_id in registered:
            continue

        swept.append(full_id)
        swept_set.add(full_id)
        title = v.get("title", "")
        fx, reason = _match_video_to_fixture(title, v.get("date"), v.get("live_start_time"),
                                             owner_id=v["owner_id"])
        if fx:
            written = register_official_video(fx, f"https://vk.com/video{full_id}", title)
            if written:
                found += 1
                print(f"[OK] Ранее пропущенное видео {vid} — официальный матч {fx['date']} "
                      f"{fx['team1']} — {fx['team2']} (возр. {fx.get('age') or '?'}): {title}")
        else:
            before = len(queue)
            _queue_unresolved(state, v, title, v.get("description", ""), reason)
            queued += len(queue) - before

    if len(swept) > 5000:
        del swept[:-5000]
    if found or queued:
        print(f"[INFO] Группа {group_id}: ранее пропущенных видео — привязано {found}, в очередь {queued}")
        save_state(state)


'''

content = TARGET.read_text(encoding="utf-8")
if "def _sweep_unplaced(" in content:
    print("Уже применено.")
    sys.exit(0)
if "def _match_video_to_fixture(title: str, upload_ts=None, live_start=None, owner_id=None)" not in content:
    print("ВНИМАНИЕ: сначала примените fixes_oct3_patch.py — файл НЕ изменён")
    sys.exit(1)
missing = [n for n, s in (("цикл новых видео", CALL_ANCHOR), ("check_groups_once", FUNC_ANCHOR)) if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_sweep"))
content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
content = content.replace(CALL_ANCHOR, CALL_ADD + CALL_ANCHOR)
TARGET.write_text(content, encoding="utf-8")
print("Страховка добавлена (резервная копия: vk_to_tg_hockey_bot.py.bak_sweep)")
