#!/usr/bin/env python3
"""Логотипы команд из календарей турниров (junior.fhr.ru, spb.fhr.ru) — в справочник team_logos.json.
Уже известные логотипы не перезаписываются."""
import shutil, sys
from pathlib import Path
TARGET = Path(__file__).parent / "spb_fhr_client.py"
OLD1 = '''        team1 = teams[0].strip() if len(teams) > 0 else ""
        team2 = teams[1].strip() if len(teams) > 1 else ""
        if not team1 or not team2:
            continue
'''
NEW1 = OLD1 + '''        _remember_calendar_logos(block)
'''
OLD2 = 'def fetch_calendar_matches(session, tournament_id, year_id, domain="spb.fhr.ru", group_id=None):'
NEW2 = '''_TEAM_LOGO_RE = re.compile(
    r'<img[^>]+src="(https?://[^"]+/teams/[^"]+)"[^>]*>(?:(?!<img).){0,600}?<span class="team-title">\\s*(.*?)\\s*</span>',
    re.DOTALL)


def _remember_calendar_logos(block):
    """Логотипы команд из строки календаря — в общий справочник (известные не перезаписываются)."""
    try:
        import json as _json
        import post_standings as _st
        logos = _st._load_logo_map()
        changed = False
        for url, name in _TEAM_LOGO_RE.findall(block):
            key = _st._logo_key(re.sub(r"<[^>]+>", "", name).strip())
            if key and "default" not in url and not dict.get(logos, key):
                logos[key] = url
                changed = True
        if changed:
            _st.LOGO_MAP_FILE.write_text(_json.dumps(dict(logos), ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


''' + OLD2
c = TARGET.read_text(encoding="utf-8")
if "_remember_calendar_logos" in c:
    print("уже исправлено")
elif c.count(OLD1) != 1 or c.count(OLD2) != 1:
    sys.exit("место не найдено — файл не изменён, пришлите вывод")
else:
    shutil.copy(TARGET, TARGET.with_name("spb_fhr_client.py.bak_logos"))
    TARGET.write_text(c.replace(OLD1, NEW1).replace(OLD2, NEW2), encoding="utf-8")
    print("✓ логотипы команд из календарей турниров — в справочник")
