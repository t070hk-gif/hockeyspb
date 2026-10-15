#!/usr/bin/env python3
"""
Этап 3: vk_to_tg_hockey_bot.py
  1. Каждое новое видео сначала сопоставляется с официальным расписанием
     дня (team_matcher.py). Нашлось — регистрируется под точными ключами
     расписания, БЕЗ перезаписи уже существующих ссылок.
  2. Не нашлось — старая логика (товарищеские игры) без изменений.
  3. Похожие на матч видео, которые старая логика выбрасывает, попадают в
     очередь нераспознанных: перепроверка раз в час, сводка в личку в 21:00,
     записи старше 10 дней удаляются.

Запуск (из ~/vk-bot):  python3 stage3_patch.py
Перед изменением делает резервную копию vk_to_tg_hockey_bot.py.bak_stage3.
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

HELPERS_ANCHOR = "def check_groups_once("
HELPERS_ADD = '''# ======================= ЭТАП 3: сопоставление по расписанию =======================
import team_matcher

UNRESOLVED_RECHECK_SECONDS = 3600      # перепроверка очереди раз в час
UNRESOLVED_KEEP_DAYS = 10              # дальше — удаляем из очереди
UNRESOLVED_DIGEST_HOUR = 21            # ежедневная сводка администратору

_fixtures_cache = {"mtime": None, "data": {}}


def _get_fixtures() -> dict:
    """Официальное расписание с возрастами; перечитывается, только если
    post_schedule.py обновил файл."""
    path = team_matcher.FIXTURES_FILE if team_matcher.FIXTURES_FILE.exists() else team_matcher.OFFICIAL_KEYS_FILE
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return _fixtures_cache["data"]
    if mtime != _fixtures_cache["mtime"]:
        _fixtures_cache["data"] = team_matcher.load_fixtures()
        _fixtures_cache["mtime"] = mtime
    return _fixtures_cache["data"]


def _match_video_to_fixture(title: str, upload_ts=None, live_start=None):
    dates = team_matcher.build_date_candidates(title, live_start, upload_ts)
    return team_matcher.match_title(title, dates, fixtures=_get_fixtures(),
                                    alias_groups=team_matcher.load_alias_groups())


def register_official_video(fx: dict, video_url: str, title: str) -> list:
    """Регистрирует видео под ключами официального матча. Существующие
    ссылки НЕ перезаписываются (дубли трансляций, чужие видео под общим
    ключом без возраста). Возвращает список записанных ключей."""
    index = load_video_index()
    entry = {"video_url": video_url, "title": title}
    date, t1, t2, age = fx["date"], fx["team1"], fx["team2"], fx.get("age")

    candidates = []
    if age:
        candidates.append(f'{fx["key"]}::{age}')
        candidates.append(build_match_key_rossii(date, t1, t2, age=age))
    candidates.append(fx["key"])
    candidates.append(build_match_key_rossii(date, t1, t2))

    written = []
    for k in dict.fromkeys(candidates):
        if k not in index:
            index[k] = entry
            written.append(k)
    if written:
        save_video_index(index)
    return written


_MATCH_LIKE_RE = re.compile(r"\\s[-–—]\\s|🆚|&|\\bvs\\b|\\S-\\S", re.IGNORECASE)


def _queue_unresolved(state: dict, video: dict, title: str, description: str, reason: str) -> None:
    """Кладёт похожее на матч видео в очередь на перепроверку."""
    low = (title or "").lower()
    if any(w in low for w in team_matcher.REVIEW_WORDS):
        return
    if not _MATCH_LIKE_RE.search(title or ""):
        return
    queue = state.setdefault("_unresolved_videos", {})
    full_id = f'{video["owner_id"]}_{video["id"]}'
    if full_id in queue:
        return
    queue[full_id] = {
        "title": title, "description": description or "",
        "upload_ts": video.get("date"), "live_start": video.get("live_start_time"),
        "first_seen": int(time.time()), "reason": reason,
    }


def _recheck_unresolved(state: dict) -> None:
    """Раз в час перепроверяет очередь по свежему расписанию и синонимам."""
    now = int(time.time())
    if now - state.get("_unresolved_last_check", 0) < UNRESOLVED_RECHECK_SECONDS:
        return
    state["_unresolved_last_check"] = now
    queue = state.get("_unresolved_videos", {})
    for full_id in list(queue):
        item = queue[full_id]
        if now - item.get("first_seen", now) > UNRESOLVED_KEEP_DAYS * 86400:
            del queue[full_id]
            continue
        fx, reason = _match_video_to_fixture(item["title"], item.get("upload_ts"), item.get("live_start"))
        if fx:
            written = register_official_video(fx, f"https://vk.com/video{full_id}", item["title"])
            print(f'[OK] Из очереди: {fx["date"]} {fx["team1"]} — {fx["team2"]} '
                  f'({"записано" if written else "видео уже было"}): {item["title"]}')
            del queue[full_id]
        else:
            item["reason"] = reason
    save_state(state)


def _send_unresolved_digest(state: dict) -> None:
    """Раз в день присылает администратору список нераспознанных видео за
    последние сутки — их можно переслать боту в ручной диалог."""
    now = datetime.now()
    today = now.strftime("%d.%m.%Y")
    if now.hour < UNRESOLVED_DIGEST_HOUR or state.get("_unresolved_last_digest") == today:
        return
    state["_unresolved_last_digest"] = today
    cutoff = int(time.time()) - 86400
    items = [(fid, it) for fid, it in state.get("_unresolved_videos", {}).items()
             if it.get("first_seen", 0) >= cutoff]
    save_state(state)
    if not items:
        return
    lines = [f"📋 Нераспознанные видео за сутки: {len(items)}", ""]
    for fid, it in items[:25]:
        lines.append(f'• {it["title"][:80]}')
        lines.append(f'  https://vk.com/video{fid}  ({it.get("reason", "")})')
    if len(items) > 25:
        lines.append(f"… и ещё {len(items) - 25}")
    lines.append("")
    lines.append("Чтобы добавить видео вручную — перешлите ссылку сюда.")
    send_admin_message("\\n".join(lines))


'''

START_ANCHOR = "    process_pending_friendly_matches(state)\n"
START_ADD = '''    _recheck_unresolved(state)
    _send_unresolved_digest(state)
'''

PARSE_ANCHOR = '''            parsed = parse_video_title(title, description, upload_timestamp=upload_ts,
                                        live_start_time=live_start, extra_known_teams=extra_teams)
'''
PARSE_ADD = '''
            # Этап 3: сначала ищем видео в официальном расписании дня.
            fx, fx_reason = _match_video_to_fixture(title, upload_ts, live_start)
            if fx:
                video_url = f"https://vk.com/video{video['owner_id']}_{video['id']}"
                written = register_official_video(fx, video_url, title)
                print(f"[OK] Видео {video['id']} — официальный матч {fx['date']} "
                      f"{fx['team1']} — {fx['team2']} (возр. {fx.get('age') or '?'})"
                      f"{'' if written else ', ссылка уже была'}: {title}")
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue
'''

SKIP1_OLD = '''            if not parsed["teams"] and not parsed["date"]:
                seen_video_ids.add(video["id"])
                continue
'''
SKIP1_NEW = '''            if not parsed["teams"] and not parsed["date"]:
                _queue_unresolved(state, video, title, description, fx_reason)
                seen_video_ids.add(video["id"])
                continue
'''

SKIP2_OLD = '''                print(f"[SKIP] Видео {video['id']} — команды не найдены или не подтверждены "
                      f"официальным списком, не публикуем в общий чат: {title}")
'''
SKIP2_NEW = SKIP2_OLD + '''                _queue_unresolved(state, video, title, description, fx_reason)
'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "def register_official_video(" in content:
        print("Этап 3 уже применён — ничего не делаю.")
        return
    if not (Path(__file__).parent / "team_matcher.py").exists():
        print("ВНИМАНИЕ: рядом нет team_matcher.py — сначала скачайте его. Файл НЕ изменён.")
        sys.exit(1)

    checks = [
        ("место для функций", HELPERS_ANCHOR),
        ("начало прогона", START_ANCHOR),
        ("разбор заголовка", PARSE_ANCHOR),
        ("пропуск без команд и даты", SKIP1_OLD),
        ("пропуск неподтверждённых команд", SKIP2_OLD),
    ]
    missing = [name for name, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing))
        print("Файл НЕ изменён.")
        sys.exit(1)

    shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_stage3"))
    content = content.replace(HELPERS_ANCHOR, HELPERS_ADD + HELPERS_ANCHOR, 1)
    content = content.replace(START_ANCHOR, START_ANCHOR + START_ADD)
    content = content.replace(PARSE_ANCHOR, PARSE_ANCHOR + PARSE_ADD)
    content = content.replace(SKIP1_OLD, SKIP1_NEW)
    content = content.replace(SKIP2_OLD, SKIP2_NEW)
    TARGET.write_text(content, encoding="utf-8")
    print("Этап 3 применён (резервная копия: vk_to_tg_hockey_bot.py.bak_stage3)")


if __name__ == "__main__":
    main()
