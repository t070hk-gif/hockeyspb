#!/usr/bin/env python3
"""
Разовая перепубликация ВСЕХ турнирных таблиц (Первенство 2009–2015,
Кубок Федерации 2016–2018): новым постом с закрепом, предыдущий убирается.

    python3 force_repost_standings.py          — дождаться окончания всех матчей
                                                 сегодняшнего дня (проверка раз в
                                                 5 минут, крайний срок 23:30), затем
                                                 перепубликовать
    python3 force_repost_standings.py --now    — перепубликовать сразу

Запускать можно в фоне:  nohup python3 force_repost_standings.py > repost_log.txt 2>&1 &
"""
import fcntl
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import post_standings as st

CHECK_EVERY = 300
DEADLINE = (23, 30)


def tables():
    for age, year_id in st.PERVENSTVO_YEAR_IDS.items():
        yield age, "ПЕРВЕНСТВО", st.PERVENSTVO_SLUG, year_id
    for age, year_id in st.KUBOK_FEDERATION_YEAR_IDS.items():
        yield age, "КУБОК ФЕДЕРАЦИИ", st.KUBOK_FEDERATION_SLUG, year_id


def log(msg):
    print(f"[{datetime.now():%d.%m %H:%M:%S}] {msg}", flush=True)


def wait_for_today():
    today = datetime.now().strftime("%d.%m.%Y")
    while True:
        scheduled = finished = 0
        for age, _, slug, _ in tables():
            try:
                s, f = st._day_progress(age, slug, today)
            except Exception as e:
                log(f"не удалось проверить {age}: {e}")
                s, f = 0, 0
            scheduled += s
            finished += f
        now = datetime.now()
        if scheduled == 0:
            log("Сегодня матчей нет — публикую сразу")
            return
        if finished >= scheduled:
            log(f"Все матчи дня сыграны ({finished} из {scheduled}) — публикую")
            return
        if (now.hour, now.minute) >= DEADLINE:
            log(f"Уже {DEADLINE[0]}:{DEADLINE[1]:02d}, сыграно {finished} из {scheduled} — публикую с тем, что есть")
            return
        log(f"Сыграно {finished} из {scheduled} — жду {CHECK_EVERY // 60} мин")
        time.sleep(CHECK_EVERY)


def main():
    if "--now" not in sys.argv:
        wait_for_today()

    # Та же блокировка, что у прогонов по cron: дожидаемся, пока текущий закончится.
    lock_file = open(Path(st.__file__).parent / "post_standings.lock", "w")
    log("Жду свободной блокировки (если идёт прогон по cron)…")
    fcntl.flock(lock_file, fcntl.LOCK_EX)

    refresh = getattr(st, "_process_tournament_single_post", st.process_tournament)
    state = st.load_state()
    today = datetime.now().strftime("%d.%m.%Y")
    done = 0
    for age, ttype, slug, year_id in tables():
        try:
            refresh(age, ttype, slug, year_id, state, False)     # свежие данные и картинка
        except Exception as e:
            log(f"{age} {ttype}: не удалось обновить ({e})")
        key = f"{slug}_{year_id}"
        entry = state.get(key)
        if not entry or not st._table_images(entry, key):
            log(f"{age} {ttype}: таблицы пока нет — пропускаю")
            continue
        try:
            old_ids = entry.get("message_ids") or [entry["message_id"]]
            if st._republish_table(entry, key, age, st.format_standings_title(age, ttype)):
                entry["reposted_on"] = today
                st.save_state(state)
                done += 1
                log(f"{age} {ttype}: опубликована заново ({len(entry['message_ids'])} карт.), старые {old_ids} убраны")
            time.sleep(2)
        except Exception as e:
            log(f"{age} {ttype}: ошибка публикации ({e})")
    log(f"Готово: перепубликовано таблиц — {done}")


if __name__ == "__main__":
    main()
