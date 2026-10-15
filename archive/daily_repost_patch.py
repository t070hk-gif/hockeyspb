#!/usr/bin/env python3
"""
post_standings.py: в конце игрового дня таблица публикуется заново.

Когда у всех матчей сегодняшнего дня в турнире (возраст Первенства или
Кубка Федерации) появился результат на fhspb.ru, бот публикует таблицу
НОВЫМ постом, закрепляет его и удаляет предыдущий. Если к 23:30 часть
матчей дня осталась без результата — перепубликует с тем, что есть.
Один раз в день на таблицу; в дни без игр ничего не делает.

Предыдущий пост старше 48 часов Telegram удалить не даст — тогда с него
снимается закреп, а подпись меняется на «⬇️ Таблица обновлена — актуальная ниже».

Запуск (из ~/vk-bot):  python3 daily_repost_patch.py
Резервная копия: post_standings.py.bak_repost
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"
ANCHOR = 'if __name__ == "__main__":'

ADD = '''# ===================== Перепубликация таблицы в конце игрового дня =====================
from datetime import datetime
REPOST_FALLBACK_HOUR, REPOST_FALLBACK_MINUTE = 23, 30
KUBOK_FEDERATION_FHSPB = {"2016": [6583], "2017": [6584], "2018": [6585]}
_CHESS_MATCH_RE = re.compile(r'MatchID=(\\d+)"[^>]*title="[^"]*?(\\d{2}\\.\\d{2}\\.\\d{4})"')


def _fhspb_tournament_ids(age, tournament_slug):
    if tournament_slug == PERVENSTVO_SLUG:
        return [tid for _, tid in FHSPB_PERVENSTVO.get(age, [])]
    return KUBOK_FEDERATION_FHSPB.get(age, [])


def _day_progress(age, tournament_slug, day):
    """(матчей на день по расписанию, из них с результатом на fhspb.ru)."""
    tids = {str(t) for t in _fhspb_tournament_ids(age, tournament_slug)}
    if not tids:
        return 0, 0
    fixtures_file = Path(__file__).parent / "official_fixtures.json"
    try:
        fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))
    except Exception:
        return 0, 0
    scheduled = {(f["key"], f.get("age")) for f in fixtures
                 if f.get("date") == day and str(f.get("tournament_id")) in tids}
    if not scheduled:
        return 0, 0
    finished = set()
    for tid in tids:
        page = fetch_with_retry(f"https://fhspb.ru/Standings?TournamentID={tid}")
        finished.update(mid for mid, d in _CHESS_MATCH_RE.findall(page) if d == day)
    return len(scheduled), len(finished)


def _retire_old_table(message_id):
    """Удаляет старый пост таблицы; если нельзя (старше 48 ч) — снимает
    закреп и помечает, что актуальная таблица ниже."""
    base = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    r = _tg_post(f"{base}/deleteMessage", data={"chat_id": TG_CHAT_ID, "message_id": message_id}).json()
    if r.get("ok") or "not found" in str(r.get("description", "")):
        return
    _tg_post(f"{base}/unpinChatMessage", data={"chat_id": TG_CHAT_ID, "message_id": message_id})
    _tg_post(f"{base}/editMessageCaption", data={"chat_id": TG_CHAT_ID, "message_id": message_id,
                                                 "caption": "⬇️ Таблица обновлена — актуальная ниже"})
    print(f"[INFO] Старую таблицу {message_id} удалить нельзя (старше 48 ч) — снят закреп, подпись заменена")


def _maybe_daily_repost(age, tournament_type, tournament_slug, year_id, state, dry_run, was_new):
    state_key = f"{tournament_slug}_{year_id}"
    entry = state.get(state_key)
    now = datetime.now()
    today = now.strftime("%d.%m.%Y")
    if not entry or entry.get("reposted_on") == today:
        return
    if was_new:
        entry["reposted_on"] = today     # таблицу и так только что опубликовали
        save_state(state)
        return
    image_path = IMAGES_DIR / f"{state_key}.png"
    if not image_path.exists():
        return
    scheduled, finished = _day_progress(age, tournament_slug, today)
    if not scheduled or not finished:
        return
    late = (now.hour, now.minute) >= (REPOST_FALLBACK_HOUR, REPOST_FALLBACK_MINUTE)
    if finished < scheduled and not late:
        return
    print(f"\\n[ПЕРЕПУБЛИКАЦИЯ ТАБЛИЦЫ] {age} г.р. {tournament_type}: сыграно {finished} из {scheduled}")
    if dry_run:
        print("  (dry-run — не отправлено)")
        return
    old_id = entry["message_id"]
    new_id = send_photo(TOPIC_IDS[age], image_path, caption=format_standings_title(age, tournament_type))
    pin_message(new_id)
    entry["message_id"] = new_id
    entry["reposted_on"] = today
    save_state(state)
    _retire_old_table(old_id)


_process_tournament_single_post = process_tournament


def process_tournament(age, tournament_type, tournament_slug, year_id, state, dry_run):
    """Обычное обновление таблицы + перепубликация в конце игрового дня."""
    was_new = f"{tournament_slug}_{year_id}" not in state
    _process_tournament_single_post(age, tournament_type, tournament_slug, year_id, state, dry_run)
    try:
        _maybe_daily_repost(age, tournament_type, tournament_slug, year_id, state, dry_run, was_new)
    except Exception as e:
        print(f"[WARN] Перепубликация {age} {tournament_type}: {e}")


'''

content = TARGET.read_text(encoding="utf-8")
if "_maybe_daily_repost" in content:
    print("Уже применено.")
    sys.exit(0)
if "FHSPB_PERVENSTVO" not in content or "def _tg_post(" not in content:
    print("ВНИМАНИЕ: сначала примените fhspb_standings_patch.py и standings_resilience_patch.py — файл НЕ изменён")
    sys.exit(1)
if content.count(ANCHOR) != 1:
    print("ВНИМАНИЕ: место не найдено однозначно — файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_repost"))
TARGET.write_text(content.replace(ANCHOR, ADD + ANCHOR), encoding="utf-8")
print("Перепубликация в конце игрового дня добавлена (резервная копия: post_standings.py.bak_repost)")
