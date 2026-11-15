#!/usr/bin/env python3
"""
Быстрый, лёгкий процесс для LIVE-матчей — запускается гораздо чаще, чем
основной post_schedule.py (например, раз в 30-60 секунд через cron), но
НЕ делает полный обход всех турниров каждый раз. Вместо этого читает
"снимок" (live_snapshot.json), который post_schedule.py сохраняет при
каждом своём полном прогоне — там уже есть список матчей каждого дня,
включая их время и связь с spb.fhr.ru/junior.fhr.ru (game_id).

Логика:
1. Загружаем live_snapshot.json — для каждого поста дня там уже есть
   список матчей (без необходимости заново скачивать расписание турнира).
2. Оставляем только те матчи, что ПРЯМО СЕЙЧАС идут (is_match_live).
3. Для каждого такого матча — если он привязан к spb.fhr.ru/junior.fhr.ru
   (то есть в spb_lookup для этого поста есть game_id) — запрашиваем
   ТОЛЬКО страницу этого конкретного матча (быстро, один HTTP-запрос),
   а не всё расписание турнира заново.
4. Если появился новый гол — пересобираем caption для ВСЕГО поста дня
   (используя матчи из снимка, не требуя нового похода на fhspb.ru) и
   редактируем существующее сообщение в Telegram.

ВАЖНО: этот скрипт НЕ публикует новые посты и не трогает счёт/данные
матчей, что уже закончились или ещё не начались — этим занимается
основной post_schedule.py на своём обычном 2-минутном цикле. Единственная
задача live_watcher.py — как можно быстрее показывать НОВЫЕ голы у уже
идущих матчей.
"""

import argparse
import builtins
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import post_schedule as sched

_original_print = builtins.print


def print(*args, **kwargs):
    timestamp = datetime.now().strftime("%d.%m %H:%M:%S")
    _original_print(f"[{timestamp}]", *args, **kwargs)

try:
    import spb_fhr_client
except ImportError:
    spb_fhr_client = None

LIVE_LOCK_FILE = Path(__file__).parent / "live_watcher.lock"


def _acquire_lock() -> bool:
    if LIVE_LOCK_FILE.exists():
        try:
            old_pid = int(LIVE_LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    LIVE_LOCK_FILE.write_text(str(os.getpid()))
    return True


def _release_lock():
    LIVE_LOCK_FILE.unlink(missing_ok=True)


def load_live_snapshot() -> dict:
    if not sched.LIVE_SNAPSHOT_FILE.exists():
        return {}
    return json.loads(sched.LIVE_SNAPSHOT_FILE.read_text(encoding="utf-8"))


def run_once(dry_run: bool) -> None:
    if spb_fhr_client is None:
        print("[WARN] spb_fhr_client недоступен — нечего обновлять")
        return

    snapshot = load_live_snapshot()
    if not snapshot:
        print("[INFO] Снимок пуст (post_schedule.py ещё не сохранил его) — пропускаем")
        return

    state = sched.load_state()
    video_index = sched.load_video_index()
    spb_details_cache = sched.load_spb_details_cache()

    spb_session = None
    spb_rossii_session = None
    checked_domains = set()

    updated_count = 0

    for state_key, entry in snapshot.items():
        date_label = entry["date_label"]
        day_matches = entry["matches"]
        spb_lookup = entry["spb_lookup"]
        age = entry["age"]
        domain = entry["domain"]

        # Есть ли среди матчей этого поста хоть один ПРЯМО СЕЙЧАС живой?
        live_matches = [m for m in day_matches if sched.is_match_worth_fast_checking(date_label, m["time"])]
        if not live_matches:
            continue  # ничего срочного в этом посте — пропускаем, не тратим запросы

        # Сессию создаём ЛЕНИВО — только если реально понадобилась (есть
        # живой матч) и только один раз за прогон на домен.
        if domain == "spb.fhr.ru" and "spb.fhr.ru" not in checked_domains:
            try:
                spb_session = spb_fhr_client.create_session()
            except Exception as e:
                print(f"[WARN] Не удалось создать сессию spb.fhr.ru: {e}")
            checked_domains.add("spb.fhr.ru")
        elif domain == spb_fhr_client.KUBOK_ROSSII_DOMAIN and domain not in checked_domains:
            try:
                spb_rossii_session = spb_fhr_client.create_session_kubok_rossii()
            except Exception as e:
                print(f"[WARN] Не удалось создать сессию {domain}: {e}")
            checked_domains.add(domain)

        session = spb_session if domain == "spb.fhr.ru" else spb_rossii_session
        if session is None:
            continue

        # Пересобираем caption целиком (не только для живых матчей, а для
        # ВСЕХ матчей этого дня) — format_caption сама решает, кому нужны
        # свежие данные (см. is_match_live внутри неё), а кому нет.
        is_rossii = domain == spb_fhr_client.KUBOK_ROSSII_DOMAIN
        caption = sched.format_caption(date_label, day_matches, video_index, spb_lookup,
                                        session, spb_details_cache, domain=domain, age=age)

        existing = state.get(state_key)
        if existing is None:
            continue  # поста ещё нет — не наша забота
        # live-счёт теперь на баннере: перерисовываем картинку, если счёт/голы изменились
        img, img_fp = None, existing.get("image_fp")
        if existing.get("banner") and Path(existing["banner"]).exists():
            img, img_fp = sched._results_image(state_key, Path(existing["banner"]), day_matches, spb_lookup,
                                               existing.get("title", ""), existing.get("image_fp"))
        image_changed = img is not None and img_fp != existing.get("image_fp")
        if existing.get("caption") == caption and not image_changed:
            continue  # ничего не изменилось

        print(f"[LIVE-ОБНОВЛЕНИЕ{' + баннер' if image_changed else ''}] {state_key} — {date_label}")
        if not dry_run:
            try:
                if image_changed:
                    sched.edit_media(existing["message_id"], img, caption, entry.get("topic_id"))
                    existing["image_fp"] = img_fp
                else:
                    sched.edit_caption(existing["message_id"], caption)
                existing["caption"] = caption
                sched.save_state(state)
                updated_count += 1
            except Exception as e:
                print(f"[ERROR] Не удалось обновить {state_key}: {e}")
        else:
            print("  (dry-run — не отправлено)")

    sched.save_spb_details_cache(spb_details_cache)
    print(f"Обновлено постов: {updated_count}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.live and not args.dry_run:
        print("Укажите --dry-run (тест) или --live (реальная отправка)")
        sys.exit(1)

    if not _acquire_lock():
        print("[INFO] Предыдущий прогон live_watcher.py, судя по всему, ещё выполняется — пропускаем.")
        return

    try:
        run_once(dry_run=not args.live)
    finally:
        _release_lock()


if __name__ == "__main__":
    main()
