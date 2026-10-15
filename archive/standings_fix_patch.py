#!/usr/bin/env python3
"""
post_standings.py:
  1. Пустые группы (матчей ещё не было) пропускаются; если пусто всё —
     таблица не публикуется.
  2. Названия, которых нет в NAME_DISPLAY_OVERRIDES, приводятся к
     аккуратному виду: слова КАПСОМ -> С заглавной, аббревиатуры
     (СКА, ХКД, ХК, ЖХК, СШ ...) остаются как есть.

Запуск (из ~/vk-bot):  python3 standings_fix_patch.py
Резервная копия: post_standings.py.bak_fix
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

EMPTY_OLD = '''    by_group = fetch_standings_by_group(tournament_slug, year_id)
    if not by_group:
        return
'''
EMPTY_NEW = '''    by_group = fetch_standings_by_group(tournament_slug, year_id)
    # Группы без команд (матчей ещё не было) не показываем; если пусто
    # всё — таблицу не публикуем, иначе вышла бы картинка с одним заголовком.
    by_group = {g: s for g, s in by_group.items() if s}
    if not by_group:
        return
'''

NAME_OLD = '''    return NAME_DISPLAY_OVERRIDES.get(team_name, team_name)
'''
NAME_NEW = '''    if team_name in NAME_DISPLAY_OVERRIDES:
        return NAME_DISPLAY_OVERRIDES[team_name]
    return _prettify_team_name(team_name)


_KEEP_UPPER = {"СКА", "ХКД", "ХК", "ЖХК", "СШ", "СШОР", "ГУАП", "МАХ", "ЦСКА", "ВВС", "УОР"}


def _prettify_team_name(name):
    """Названия не из списка исправлений: слова КАПСОМ -> С заглавной,
    аббревиатуры остаются. 'ХК "НЕВСКИЙ" 2011' -> 'ХК "Невский" 2011'."""
    def fix(word):
        core = word.strip('"«»()')
        if len(core) > 3 and core.isupper() and core.isalpha() and core not in _KEEP_UPPER:
            return word.replace(core, core.capitalize())
        return word
    return " ".join(fix(w) for w in name.split(" "))
'''

content = TARGET.read_text(encoding="utf-8")
if "_prettify_team_name" in content:
    print("Уже применено.")
    sys.exit(0)
missing = [n for n, s in (("пустые группы", EMPTY_OLD), ("названия", NAME_OLD)) if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_fix"))
content = content.replace(EMPTY_OLD, EMPTY_NEW).replace(NAME_OLD, NAME_NEW)
TARGET.write_text(content, encoding="utf-8")
print("Готово (резервная копия: post_standings.py.bak_fix)")
