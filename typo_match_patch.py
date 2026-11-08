#!/usr/bin/env python3
"""
team_matcher.py: автоматическое сопоставление прощает опечатки в названиях команд.
Если заголовок не подошёл ни к одному матчу, длинные слова (от 6 букв) сверяются
с названиями команд, играющих в эти дни; слово с опечаткой заменяется на самое
похожее (сходство ≥ 84%, та же первая буква), и сопоставление повторяется.
Пример: «СКА СЕРЕБРЧНЫЕ ЛЬВЫ» → «СКА СЕРЕБРЯНЫЕ ЛЬВЫ».

team_aliases.json: синоним «АКМ» = «Академия Михайлова».

Запуск (из ~/vk-bot):  python3 typo_match_patch.py
"""
import json
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "team_matcher.py"

OLD = '''def match_title(title: str, date_candidates: list, fixtures: dict = None,
                alias_groups: list = None, start_dt=None):'''
NEW = '''def match_title(title: str, date_candidates: list, fixtures: dict = None,
                alias_groups: list = None, start_dt=None):
    """Сопоставление; если не нашлось — повтор с исправленными опечатками в названиях команд."""
    fx, why = _match_title_exact(title, date_candidates, fixtures, alias_groups, start_dt)
    if fx is not None:
        return fx, why
    fixed, changes = _fix_typos(title, date_candidates, fixtures, alias_groups)
    if not changes:
        return fx, why
    fx2, why2 = _match_title_exact(fixed, date_candidates, fixtures, alias_groups, start_dt)
    if fx2 is None:
        return fx, why
    return fx2, f"{why2} (исправлена опечатка: {', '.join(changes)})"


def _fix_typos(title, date_candidates, fixtures, alias_groups, min_ratio=0.84):
    """Заменяет в заголовке слова-опечатки (от 6 букв) на похожие слова из названий команд этих дней."""
    import difflib
    if fixtures is None:
        fixtures = load_fixtures()
    vocab = set()
    for d in date_candidates or []:
        for f in fixtures.get(d, []):
            for team in (f.get("team1", ""), f.get("team2", "")):
                vocab.update(w for w in re.findall(r"[а-яё]+", team.lower()) if len(w) >= 5)
    for group in alias_groups or []:
        for name in group:
            vocab.update(w for w in re.findall(r"[а-яё]+", name.lower()) if len(w) >= 5)
    if not vocab:
        return title, []
    changes = []

    def repl(m):
        word = m.group(0)
        low = word.lower().replace("ё", "е")
        if len(low) < 6 or low in vocab:
            return word
        best, score = None, 0.0
        for v in vocab:
            if v[0] != low[0] or abs(len(v) - len(low)) > 2:
                continue
            r = difflib.SequenceMatcher(None, low, v).ratio()
            if r > score:
                best, score = v, r
        if best and score >= min_ratio:
            changes.append(f"{word}→{best}")
            return best.upper() if word.isupper() else best
        return word
    fixed = re.sub(r"[А-Яа-яЁё]+", repl, title)
    return fixed, changes


def _match_title_exact(title: str, date_candidates: list, fixtures: dict = None,
                       alias_groups: list = None, start_dt=None):'''

TEST_ADD = '''

def test_typo_tolerant_match():
    """Сопоставление прощает опечатку в названии, но не подменяет непохожие команды."""
    import team_matcher as tm
    d = "08.11.2026"
    fx = {d: [{"date": d, "team1": "армия ска", "team2": "ска серебряные львы", "age": "10",
               "key": f"{d}::армия ска|ска серебряные львы", "time": "13:45"}]}
    r, why = tm.match_title('МАТЧ ХК "АРМИЯ СКА 2010" & ХК "СКА СЕРЕБРЧНЫЕ ЛЬВЫ 2010"', [d], fixtures=fx, alias_groups=[])
    assert r and r["age"] == "10" and "опечатка" in why, why
    r, why = tm.match_title('АРМИЯ СКА 2010 - СКА СТРЕЛЬНА 2010', [d], fixtures=fx, alias_groups=[])
    assert r is None, r
'''


def main():
    c = TARGET.read_text(encoding="utf-8")
    if "def _fix_typos" in c:
        print("team_matcher.py: уже исправлено")
    else:
        if c.count(OLD) != 1:
            sys.exit("team_matcher.py: место не найдено — файл НЕ изменён")
        shutil.copy(TARGET, TARGET.with_name("team_matcher.py.bak_typo"))
        TARGET.write_text(c.replace(OLD, NEW), encoding="utf-8")
        print("team_matcher.py: сопоставление прощает опечатки в названиях команд")
    ap = BASE / "team_aliases.json"
    groups = json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else []
    g = ["академия михайлова", "акм"]
    if not any(set(g) <= set(x) for x in groups):
        groups.append(g)
        ap.write_text(json.dumps(groups, ensure_ascii=False, indent=1), encoding="utf-8")
        print("team_aliases.json: синоним «АКМ» = «Академия Михайлова»")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_typo_tolerant_match" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест опечаток")


if __name__ == "__main__":
    main()
