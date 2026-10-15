#!/usr/bin/env python3
"""
post_standings.py: турнирная таблица с группами — альбом в одном посте,
отдельная картинка на каждую группу (А и Б, группы 1 и 2, группы Кубка
Федерации). Таблица без групп — одна картинка, как раньше.

  * новая таблица — альбом, первое фото закрепляется;
  * обновление — картинки альбома правятся на месте;
  * нынешние таблицы «все группы на одной картинке» на ближайшем прогоне
    переопубликуются альбомом, старый пост убирается (старше 48 ч — снимается
    закреп и меняется подпись);
  * вечерняя перепубликация тоже работает с альбомами.

Нужны применённые daily_repost_patch.py и standings_resilience_patch.py.
Запуск (из ~/vk-bot):  python3 standings_album_patch.py
Резервная копия: post_standings.py.bak_album
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

HELPERS = '''def send_album(topic_id, image_paths, caption=""):
    """Альбом из нескольких картинок одним постом; подпись — у первой.
    Возвращает id сообщений альбома по порядку."""
    media = [dict({"type": "photo", "media": f"attach://p{i}"},
                  **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {}))
             for i in range(len(image_paths))]
    files = {f"p{i}": open(p, "rb") for i, p in enumerate(image_paths)}
    try:
        resp = _tg_post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup",
                        data={"chat_id": TG_CHAT_ID, "message_thread_id": topic_id,
                              "media": json.dumps(media), "disable_notification": True},
                        files=files, timeout=60)
    finally:
        for f in files.values():
            f.close()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendMediaGroup error: {result}")
    return [m["message_id"] for m in result["result"]]


def _table_images(entry, state_key):
    """Картинки уже нарисованной таблицы (одна или по группам) — или []."""
    ids = entry.get("message_ids") or [entry["message_id"]]
    if len(ids) > 1:
        paths = [IMAGES_DIR / f"{state_key}_{i + 1}.png" for i in range(len(ids))]
    else:
        paths = [IMAGES_DIR / f"{state_key}.png"]
    return paths if all(p.exists() for p in paths) else []


def _republish_table(entry, state_key, age, title):
    """Публикует таблицу заново (альбом или фото), закрепляет, убирает старые сообщения."""
    paths = _table_images(entry, state_key)
    if not paths:
        return False
    old_ids = entry.get("message_ids") or [entry["message_id"]]
    ids = send_album(TOPIC_IDS[age], paths, title) if len(paths) > 1 \\
        else [send_photo(TOPIC_IDS[age], paths[0], caption=title)]
    pin_message(ids[0])
    entry["message_id"], entry["message_ids"] = ids[0], ids
    for old in old_ids:
        _retire_old_table(old)
    return True


'''

PROCESS_NEW = '''def process_tournament(age, tournament_type, tournament_slug, year_id, state, dry_run):
    topic_id = TOPIC_IDS[age]

    by_group = fetch_standings_by_group(tournament_slug, year_id)
    _remember_logos(by_group)
    if tournament_slug == PERVENSTVO_SLUG:
        by_group = fhspb_pervenstvo_standings(age, by_group)
    # Группы без команд (матчей ещё не было) не показываем; если пусто
    # всё — таблицу не публикуем.
    by_group = {g: s for g, s in by_group.items() if s}
    if not by_group:
        return

    title = format_standings_title(age, tournament_type)
    state_key = f"{tournament_slug}_{year_id}"
    fingerprint = json.dumps({"data": by_group, "overrides": NAME_DISPLAY_OVERRIDES,
                              "local_logos": LOCAL_LOGO_OVERRIDES}, ensure_ascii=False, sort_keys=True)

    groups = list(by_group)
    album = len(groups) > 1           # несколько групп — альбом, картинка на группу
    existing = state.get(state_key)
    old_ids = (existing.get("message_ids") or [existing["message_id"]]) if existing else []
    same_shape = existing is not None and len(old_ids) == (len(groups) if album else 1)

    if same_shape and existing.get("fingerprint") == fingerprint:
        return
    label = ("НОВАЯ ТАБЛИЦА" if existing is None else
             "ОБНОВЛЕНИЕ ТАБЛИЦЫ" if same_shape else "ТАБЛИЦА ПО ГРУППАМ")
    word = "группы" if 2 <= len(groups) <= 4 else "групп"
    print(f"\\n[{label}] {age} г.р. {tournament_type}" + (f" ({len(groups)} {word})" if album else ""))
    if dry_run:
        print("  (dry-run — не отправлено)")
        return

    if album:
        paths = []
        for i, g in enumerate(groups):
            path = IMAGES_DIR / f"{state_key}_{i + 1}.png"
            draw_standings_image(title, {g: by_group[g]}, path)
            paths.append(path)
    else:
        paths = [IMAGES_DIR / f"{state_key}.png"]
        draw_standings_image(title, by_group, paths[0])

    if same_shape:
        try:
            for i, (mid, path) in enumerate(zip(old_ids, paths)):
                edit_photo(mid, path, caption=title if i == 0 else "")
            existing["fingerprint"] = fingerprint
            save_state(state)
            time.sleep(1)
            return
        except RuntimeError as e:
            if "message to edit not found" not in str(e):
                raise
            print("[INFO] Сообщение таблицы удалено — публикую заново")

    # Новая таблица, смена вида (одна картинка <-> альбом) или удалённое сообщение
    ids = send_album(topic_id, paths, title) if album else [send_photo(topic_id, paths[0], caption=title)]
    pin_message(ids[0])
    entry = {"message_id": ids[0], "message_ids": ids, "fingerprint": fingerprint}
    if existing and existing.get("reposted_on"):
        entry["reposted_on"] = existing["reposted_on"]
    state[state_key] = entry
    save_state(state)
    for old in old_ids:
        _retire_old_table(old)
    time.sleep(1)
'''

REPOST_CHECK_OLD = '''    image_path = IMAGES_DIR / f"{state_key}.png"
    if not image_path.exists():
        return
'''
REPOST_CHECK_NEW = '''    if not _table_images(entry, state_key):
        return
'''
REPOST_SEND_OLD = '''    old_id = entry["message_id"]
    new_id = send_photo(TOPIC_IDS[age], image_path, caption=format_standings_title(age, tournament_type))
    pin_message(new_id)
    entry["message_id"] = new_id
    entry["reposted_on"] = today
    save_state(state)
    _retire_old_table(old_id)
'''
REPOST_SEND_NEW = '''    if _republish_table(entry, state_key, age, format_standings_title(age, tournament_type)):
        entry["reposted_on"] = today
        save_state(state)
'''


def replace_first_function(content, name, new_code):
    """Заменяет ПЕРВОЕ определение функции верхнего уровня целиком."""
    start = content.index(f"def {name}(")
    pos = content.index("\n", start) + 1
    while pos < len(content):
        end = content.find("\n", pos)
        end = len(content) if end == -1 else end
        line = content[pos:end]
        if line.strip() and not line[0].isspace():
            break
        pos = end + 1
    return content[:start] + new_code.rstrip("\n") + "\n\n\n" + content[pos:]


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "def send_album(" in content:
        print("Уже применено.")
        return
    need = [("перепубликация (daily_repost_patch)", "def _retire_old_table("),
            ("проверка картинки при перепубликации", REPOST_CHECK_OLD),
            ("отправка при перепубликации", REPOST_SEND_OLD)]
    missing = [n for n, s in need if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_album"))
    content = content.replace(REPOST_CHECK_OLD, REPOST_CHECK_NEW).replace(REPOST_SEND_OLD, REPOST_SEND_NEW)
    content = replace_first_function(content, "process_tournament", PROCESS_NEW)
    content = content.replace("def process_tournament(", HELPERS + "def process_tournament(", 1)
    TARGET.write_text(content, encoding="utf-8")
    print("Таблицы с группами теперь публикуются альбомом (резервная копия: post_standings.py.bak_album)")


if __name__ == "__main__":
    main()
