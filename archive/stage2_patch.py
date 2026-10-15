#!/usr/bin/env python3
"""
Этап 2: post_schedule.py
  1. сохраняет расписание с возрастами в official_fixtures.json;
  2. не затирает official_matches.json при сбое сайта (слияние, срок 60 дней);
  3. дописывает недостающие команды из расписания в teams.json (разделы auto_*).

Запуск (из ~/vk-bot):  python3 stage2_patch.py
Перед изменением делает резервную копию post_schedule.py.bak_stage2.
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"

GLOBALS_ANCHOR = 'OFFICIAL_MATCHES_FILE = Path(__file__).parent / "official_matches.json"\n'
GLOBALS_ADD = '''OFFICIAL_FIXTURES_FILE = Path(__file__).parent / "official_fixtures.json"
AUTO_TEAMS_FILE = Path(__file__).parent / "teams.json"
OFFICIAL_RETENTION_DAYS = 60

# Собираются за один прогон (процесс каждый раз новый — cron):
_official_fixtures = {}      # "ключ::возраст" -> матч с возрастом
_schedule_team_names = {}    # "2016" -> {"Варяги 16", ...} как в расписании
'''

HELPERS_ANCHOR = "def process_tournament("
HELPERS_ADD = '''def _record_official_fixture(key, age_full, tournament_id, raw_team1=None, raw_team2=None):
    """Запоминает официальный матч вместе с возрастом (для team_matcher.py)
    и исходные названия команд (для автопополнения teams.json)."""
    parts = key.split("::")
    if len(parts) < 2 or "|" not in parts[1]:
        return
    team1, team2 = parts[1].split("|", 1)
    age = str(age_full)[-2:] if age_full else None
    _official_fixtures[f"{key}::{age}"] = {
        "date": parts[0], "team1": team1, "team2": team2,
        "age": age, "key": key, "tournament_id": tournament_id,
    }
    if age_full and (raw_team1 or raw_team2):
        names = _schedule_team_names.setdefault(str(age_full), set())
        for n in (raw_team1, raw_team2):
            if n:
                names.add(n)


def _is_recent(date_str):
    try:
        d = datetime.strptime(date_str, "%d.%m.%Y")
    except (ValueError, TypeError):
        return False
    return d >= datetime.now() - timedelta(days=OFFICIAL_RETENTION_DAYS)


def _auto_update_teams():
    """Дописывает в teams.json команды, которые есть в расписании, но
    отсутствуют в справочнике. Ручные разделы не трогаем — новые названия
    идут в отдельные разделы auto_<год>."""
    if not AUTO_TEAMS_FILE.exists() or not _schedule_team_names:
        return
    try:
        data = json.loads(AUTO_TEAMS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] teams.json не прочитан, автопополнение пропущено: {e}")
        return
    existing = {n for lst in data.values() for n in lst}
    added = []
    for age_full, names in sorted(_schedule_team_names.items()):
        new = sorted(n for n in names if n not in existing)
        if new:
            data.setdefault(f"auto_{age_full}", []).extend(new)
            existing.update(new)
            added.extend(new)
    if added:
        AUTO_TEAMS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[INFO] В teams.json добавлены команды из расписания: {', '.join(added)}")


def _save_official_data(official_keys):
    """Сохраняет официальные матчи СЛИЯНИЕМ со старыми данными, а не
    перезаписью: если fhspb.ru в этот прогон отдал неполное расписание
    (сбой сайта/сети), уже известные матчи не теряются. Записи старше
    OFFICIAL_RETENTION_DAYS дней удаляются."""
    old_keys = []
    if OFFICIAL_MATCHES_FILE.exists():
        try:
            old_keys = json.loads(OFFICIAL_MATCHES_FILE.read_text(encoding="utf-8"))
        except Exception:
            old_keys = []
    merged_keys = {k for k in old_keys if _is_recent(k.split("::")[0])} | set(official_keys)
    OFFICIAL_MATCHES_FILE.write_text(
        json.dumps(sorted(merged_keys), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\\nСписок официальных матчей сохранён: {len(merged_keys)} записей "
          f"(в этом прогоне собрано {len(official_keys)})")

    old_fixtures = {}
    if OFFICIAL_FIXTURES_FILE.exists():
        try:
            for fx in json.loads(OFFICIAL_FIXTURES_FILE.read_text(encoding="utf-8")):
                if _is_recent(fx.get("date")):
                    old_fixtures[f'{fx["key"]}::{fx.get("age")}'] = fx
        except Exception:
            old_fixtures = {}
    old_fixtures.update(_official_fixtures)
    fixtures = sorted(old_fixtures.values(), key=lambda f: (f["date"][6:] + f["date"][3:5] + f["date"][:2], f["key"]))
    OFFICIAL_FIXTURES_FILE.write_text(json.dumps(fixtures, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Расписание с возрастами сохранено: {len(fixtures)} матчей")

    _auto_update_teams()


'''

CUP_OLD = '''    if official_keys is not None:
        for m in matches:
            key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
            official_keys.add(key)
'''
CUP_NEW = '''    if official_keys is not None:
        for m in matches:
            key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
            official_keys.add(key)
            _record_official_fixture(key, age, tournament_id, m["team1"], m["team2"])
'''

ROSSII_OLD = '''        key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
        if official_keys is not None:
            official_keys.add(key)
'''
ROSSII_NEW = '''        key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
        if official_keys is not None:
            official_keys.add(key)
            _record_official_fixture(key, age, "kubok_rossii")
'''

SAVE_OLD = '''    OFFICIAL_MATCHES_FILE.write_text(
        json.dumps(sorted(official_keys), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\\nСписок официальных матчей сохранён: {len(official_keys)} записей")
'''
SAVE_NEW = '''    _save_official_data(official_keys)
'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "_record_official_fixture" in content:
        print("Этап 2 уже применён — ничего не делаю.")
        return

    checks = [
        ("глобальные переменные", GLOBALS_ANCHOR),
        ("место для функций", HELPERS_ANCHOR),
        ("сбор ключей (Кубок/Первенство)", CUP_OLD),
        ("сбор ключей (Кубок России)", ROSSII_OLD),
        ("сохранение списка", SAVE_OLD),
    ]
    missing = [name for name, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing))
        print("Файл НЕ изменён.")
        sys.exit(1)

    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_stage2"))

    content = content.replace(GLOBALS_ANCHOR, GLOBALS_ANCHOR + GLOBALS_ADD)
    content = content.replace(HELPERS_ANCHOR, HELPERS_ADD + HELPERS_ANCHOR, 1)
    content = content.replace(CUP_OLD, CUP_NEW)
    content = content.replace(ROSSII_OLD, ROSSII_NEW)
    content = content.replace(SAVE_OLD, SAVE_NEW)
    TARGET.write_text(content, encoding="utf-8")
    print("Этап 2 применён (резервная копия: post_schedule.py.bak_stage2)")


if __name__ == "__main__":
    main()
