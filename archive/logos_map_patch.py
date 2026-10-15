#!/usr/bin/env python3
"""
post_standings.py: общий справочник логотипов клубов (team_logos.json).
Логотип, встреченный в ЛЮБОЙ таблице spb.fhr.ru (все годы, Кубок
Федерации), запоминается и используется, если в таблице нужного года
эмблемы клуба нет.

Запуск (из ~/vk-bot):  python3 logos_map_patch.py
Резервная копия: post_standings.py.bak_logos
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

HOOK_OLD = '''    if tournament_slug == PERVENSTVO_SLUG:
        by_group = fhspb_pervenstvo_standings(age, by_group)
'''
HOOK_NEW = '''    _remember_logos(by_group)
    if tournament_slug == PERVENSTVO_SLUG:
        by_group = fhspb_pervenstvo_standings(age, by_group)
'''

LOGOS_OLD = '''    logos = {}
    for rows in (spb_by_group or {}).values():
        for r in rows:
            if r.get("logo_url"):
                logos[_logo_key(r["team"])] = r["logo_url"]
'''
LOGOS_NEW = '''    logos = _load_logo_map()
'''

FUNC_ANCHOR = "def fhspb_pervenstvo_standings("
FUNC_ADD = '''LOGO_MAP_FILE = Path(__file__).parent / "team_logos.json"
_logo_map_cache = None


def _load_logo_map():
    global _logo_map_cache
    if _logo_map_cache is None:
        try:
            _logo_map_cache = json.loads(LOGO_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            _logo_map_cache = {}
    return _logo_map_cache


def _remember_logos(by_group):
    """Запоминает логотипы клубов из таблицы spb.fhr.ru в общий справочник."""
    logos = _load_logo_map()
    changed = False
    for rows in (by_group or {}).values():
        for r in rows:
            url = r.get("logo_url")
            if url:
                key = _logo_key(r["team"])
                if logos.get(key) != url:
                    logos[key] = url
                    changed = True
    if changed:
        LOGO_MAP_FILE.write_text(json.dumps(logos, ensure_ascii=False, indent=2), encoding="utf-8")


'''

content = TARGET.read_text(encoding="utf-8")
if "_remember_logos" in content:
    print("Уже применено.")
    sys.exit(0)
checks = (("подключение", HOOK_OLD), ("сбор логотипов", LOGOS_OLD), ("функция таблицы", FUNC_ANCHOR))
missing = [n for n, s in checks if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_logos"))
content = content.replace(HOOK_OLD, HOOK_NEW).replace(LOGOS_OLD, LOGOS_NEW)
content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
TARGET.write_text(content, encoding="utf-8")
print("Готово: общий справочник логотипов (резервная копия: post_standings.py.bak_logos)")
