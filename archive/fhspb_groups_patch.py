#!/usr/bin/env python3
"""
post_standings.py: если на странице fhspb.ru несколько таблиц (турнир
разбит на группы, как Первенство 2010), берутся ВСЕ, каждая со своей
подписью "Группа X". Раньше бралась только первая.

Запуск (из ~/vk-bot):  python3 fhspb_groups_patch.py
Резервная копия: post_standings.py.bak_groups
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

OLD = '''            tables = _FHSPB_TABLE_RE.findall(page)
            rows = _parse_fhspb_table(tables[0]) if tables else []
            for r in rows:
                r["logo_url"] = logos.get(_logo_key(r["team"]))
                r["team"] = _fhspb_display_name(r["team"])
            result[label] = rows
'''
NEW = '''            found = list(_FHSPB_TABLE_RE.finditer(page))
            for i, table_match in enumerate(found, 1):
                rows = _parse_fhspb_table(table_match.group(1))
                for r in rows:
                    r["logo_url"] = logos.get(_logo_key(r["team"]))
                    r["team"] = _fhspb_display_name(r["team"])
                if len(found) == 1:
                    key = label
                else:
                    # Несколько таблиц на странице — группы внутри турнира.
                    # Название группы — ближайший заголовок перед таблицей.
                    before = page[max(0, table_match.start() - 600):table_match.start()]
                    names = re.findall(r"Группа\\s*([А-ЯA-Z0-9]+)", before)
                    sub = names[-1] if names else str(i)
                    key = f"{label}{sub}" if label else sub
                result[key] = rows
'''

content = TARGET.read_text(encoding="utf-8")
if "table_match in enumerate(found" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(OLD) != 1:
    print("ВНИМАНИЕ: место не найдено однозначно — файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_groups"))
TARGET.write_text(content.replace(OLD, NEW), encoding="utf-8")
print("Готово: берутся все группы со страницы (резервная копия: post_standings.py.bak_groups)")
