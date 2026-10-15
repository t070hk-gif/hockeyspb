#!/usr/bin/env python3
"""Самопроверка ссылок в post_schedule.py учитывает синонимы из
team_matcher.py (МАХ = Московская академия хоккея и т.п.).
Запуск: python3 selfcheck_patch.py"""
import shutil, sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"
OLD = "    return _team_recognized(team1) and _team_recognized(team2)\n"
NEW = '''    if _team_recognized(team1) and _team_recognized(team2):
        return True
    # Вторая попытка — с учётом синонимов (МАХ = Московская академия хоккея,
    # Петергоф = СКА Петергоф, Красная Машина = Красная Машина Юниор ...),
    # которые ведутся в team_matcher.py.
    try:
        import team_matcher as _tm
        tokens, _ = _tm.tokenize_title(entry.get("title") or "")
        groups = _tm.load_alias_groups()
        return all(_tm._team_spans(tokens, normalize_team_name(t), groups) for t in (team1, team2))
    except Exception:
        return False
'''

content = TARGET.read_text(encoding="utf-8")
if "import team_matcher as _tm" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(OLD) != 1:
    print("ВНИМАНИЕ: место не найдено однозначно, файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_selfcheck"))
TARGET.write_text(content.replace(OLD, NEW), encoding="utf-8")
print("Самопроверка обновлена (резервная копия: post_schedule.py.bak_selfcheck)")
