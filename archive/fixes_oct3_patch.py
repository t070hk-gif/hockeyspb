#!/usr/bin/env python3
"""
Исправления по итогам 03.10:

post_schedule.py
  * в official_fixtures.json сохраняется время матча — по нему
    team_matcher решает неоднозначность (та же пара клубов в двух
    возрастах в один день).

vk_to_tg_hockey_bot.py
  * подсказки групп: в группе «Динамо-Юниор» голое «ЖХК» = «ЖХК Динамо Юниор»;
  * в сопоставление передаётся время начала трансляции;
  * если сопоставление неоднозначно — видео НЕ регистрируется старой логикой
    под общим ключом без возраста (так видео одного возраста попадало в пост
    другого), а уходит в очередь нераспознанных и в вечернюю сводку.

Запуск (из ~/vk-bot):  python3 fixes_oct3_patch.py
Резервные копии: *.bak_oct3
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent


def patch(path, replacements, marker):
    content = path.read_text(encoding="utf-8")
    if marker in content:
        print(f"{path.name}: уже применено")
        return True
    missing = [name for name, old, _ in replacements if content.count(old) != 1]
    if missing:
        print(f"{path.name}: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
        return False
    shutil.copy(path, path.with_name(path.name + ".bak_oct3"))
    for _, old, new in replacements:
        content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print(f"{path.name}: исправлено (резервная копия: {path.name}.bak_oct3)")
    return True


# ------------------------------- post_schedule.py -------------------------------
PS = [
    ("сигнатура _record_official_fixture",
     "def _record_official_fixture(key, age_full, tournament_id, raw_team1=None, raw_team2=None):\n",
     "def _record_official_fixture(key, age_full, tournament_id, raw_team1=None, raw_team2=None, time=None):\n"),
    ("запись матча",
     '        "age": age, "key": key, "tournament_id": tournament_id,\n',
     '        "age": age, "key": key, "tournament_id": tournament_id, "time": time,\n'),
    ("вызов Кубок/Первенство",
     '            _record_official_fixture(key, age, tournament_id, m["team1"], m["team2"])\n',
     '            _record_official_fixture(key, age, tournament_id, m["team1"], m["team2"], time=m.get("time"))\n'),
    ("вызов Кубок России",
     '            _record_official_fixture(key, age, "kubok_rossii")\n',
     '            _record_official_fixture(key, age, "kubok_rossii", time=m.get("time"))\n'),
]

# ---------------------------- vk_to_tg_hockey_bot.py ----------------------------
VK = [
    ("функция сопоставления",
     '''def _match_video_to_fixture(title: str, upload_ts=None, live_start=None):
    dates = team_matcher.build_date_candidates(title, live_start, upload_ts)
    return team_matcher.match_title(title, dates, fixtures=_get_fixtures(),
                                    alias_groups=team_matcher.load_alias_groups())
''',
     '''# Подсказки по группам: как клуб называет СЕБЯ в своих трансляциях.
# Ключ — owner_id группы VK (отрицательный), значение — (шаблон, замена).
GROUP_TITLE_HINTS = {
    # «Динамо-Юниор»: «ЖХК 16 - Заневский Молот 16» = «ЖХК Динамо Юниор»
    -114375744: [(r"\\bЖХК\\b(?!\\s*[\\"«]?\\s*[А-ЯЁA-Zа-яёa-z]{3,})", "ЖХК Динамо Юниор")],
}


def _apply_group_hints(title: str, owner_id=None) -> str:
    for pattern, replacement in GROUP_TITLE_HINTS.get(owner_id, []):
        title = re.sub(pattern, replacement, title)
    return title


def _match_video_to_fixture(title: str, upload_ts=None, live_start=None, owner_id=None):
    title = _apply_group_hints(title, owner_id)
    dates = team_matcher.build_date_candidates(title, live_start, upload_ts)
    start_dt = datetime.fromtimestamp(live_start) if live_start else None
    return team_matcher.match_title(title, dates, fixtures=_get_fixtures(),
                                    alias_groups=team_matcher.load_alias_groups(),
                                    start_dt=start_dt)
'''),
    ("вызов для нового видео",
     "            fx, fx_reason = _match_video_to_fixture(title, upload_ts, live_start)\n",
     '            fx, fx_reason = _match_video_to_fixture(title, upload_ts, live_start, owner_id=video["owner_id"])\n'),
    ("вызов при перепроверке очереди",
     '        fx, reason = _match_video_to_fixture(item["title"], item.get("upload_ts"), item.get("live_start"))\n',
     '''        fx, reason = _match_video_to_fixture(item["title"], item.get("upload_ts"), item.get("live_start"),
                                             owner_id=int(full_id.rsplit("_", 1)[0]))
'''),
    ("неоднозначные — в очередь",
     '''                      f"{'' if written else ', ссылка уже была'}: {title}")
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue
''',
     '''                      f"{'' if written else ', ссылка уже была'}: {title}")
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue
            if fx_reason.startswith("неоднозначно"):
                # Не регистрируем наугад под общим ключом без возраста —
                # видео одного возраста попало бы в пост другого.
                print(f"[WARN] Видео {video['id']} — {fx_reason}; в очередь на проверку: {title}")
                _queue_unresolved(state, video, title, description, fx_reason)
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue
'''),
]


def main():
    tm = (BASE / "team_matcher.py").read_text(encoding="utf-8")
    if "start_dt=None" not in tm:
        print("ВНИМАНИЕ: сначала скачайте новый team_matcher.py — ничего не изменено")
        sys.exit(1)
    ok1 = patch(BASE / "post_schedule.py", PS, '"time": time,')
    ok2 = patch(BASE / "vk_to_tg_hockey_bot.py", VK, "GROUP_TITLE_HINTS")
    sys.exit(0 if ok1 and ok2 else 1)


if __name__ == "__main__":
    main()
