#!/usr/bin/env python3
"""
Очередь нераспознанных видео — только то, что похоже на НАШ матч:
  * в заголовке есть хотя бы одна команда из официального расписания;
  * нет города в скобках ("Сарматы 11 (Оренбург)" — другой регион);
  * не группа, предназначенная только для Кубка России (там чужие игры);
  * не студенческая лига, Первенство России, другие виды спорта и т.п.
Уже лежащий в очереди мусор удаляется при ближайшей ежечасной перепроверке.

Запуск (из ~/vk-bot):  python3 queue_filter_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_queuefilter
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

QUEUE_OLD = '''    if not _MATCH_LIKE_RE.search(title or ""):
        return
'''
QUEUE_NEW = '''    if not _MATCH_LIKE_RE.search(title or ""):
        return
    if not _looks_like_our_match(title, video.get("owner_id")):
        return
'''

RECHECK_OLD = '''        if now - item.get("first_seen", now) > UNRESOLVED_KEEP_DAYS * 86400:
            del queue[full_id]
            continue
'''
RECHECK_NEW = '''        if now - item.get("first_seen", now) > UNRESOLVED_KEEP_DAYS * 86400:
            del queue[full_id]
            continue
        if not _looks_like_our_match(item["title"], int(full_id.rsplit("_", 1)[0])):
            del queue[full_id]   # не наш матч (другой регион, студенты, другой вид спорта...)
            continue
'''

FUNC_ANCHOR = "def _queue_unresolved("
FUNC_ADD = '''QUEUE_EXCLUDE_WORDS = (
    "первенство россии", "w18", "w16", "студент", "вуз", "полпред",
    "футбол", "баскетбол", "водное поло", "плавани", "волейбол",
    "лучший игрок", "тренировк", "мастер-класс", "церемони",
)
_OTHER_CITY_RE = re.compile(r"\\([А-ЯЁ][а-яё .\\-]+\\)")   # "(Оренбург)", "(Мытищи)"


def _known_fixture_teams() -> set:
    teams = set()
    for day in _get_fixtures().values():
        for f in day:
            teams.add(f["team1"])
            teams.add(f["team2"])
    return teams


def _looks_like_our_match(title: str, owner_id=None) -> bool:
    """Похоже ли видео на матч наших турниров — иначе в очередь его не берём."""
    if owner_id is not None and abs(owner_id) in ROSSII_ONLY_GROUP_IDS:
        return False
    low = (title or "").lower()
    if any(w in low for w in team_matcher.REVIEW_WORDS) or any(w in low for w in QUEUE_EXCLUDE_WORDS):
        return False
    if _OTHER_CITY_RE.search(title or ""):
        return False
    tokens, _ = team_matcher.tokenize_title(_apply_group_hints(title, owner_id))
    groups = team_matcher.load_alias_groups()
    return any(team_matcher.mentions_team(tokens, t, groups) for t in _known_fixture_teams())


'''

content = TARGET.read_text(encoding="utf-8")
if "def _looks_like_our_match(" in content:
    print("Уже применено.")
    sys.exit(0)
if "def _apply_group_hints(" not in content:
    print("ВНИМАНИЕ: сначала примените fixes_oct3_patch.py — файл НЕ изменён")
    sys.exit(1)
checks = (("добавление в очередь", QUEUE_OLD), ("перепроверка очереди", RECHECK_OLD), ("функция очереди", FUNC_ANCHOR))
missing = [n for n, s in checks if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_queuefilter"))
content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
content = content.replace(QUEUE_OLD, QUEUE_NEW).replace(RECHECK_OLD, RECHECK_NEW)
TARGET.write_text(content, encoding="utf-8")
print("Фильтр очереди добавлен (резервная копия: vk_to_tg_hockey_bot.py.bak_queuefilter)")
