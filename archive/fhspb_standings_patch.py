#!/usr/bin/env python3
"""
Таблицы Первенства: цифры с fhspb.ru (результаты появляются сразу),
логотипы — с spb.fhr.ru (там есть все команды). Если fhspb.ru недоступен
или пуст — остаются данные spb.fhr.ru, как раньше. Посты те же самые.

Запуск (из ~/vk-bot):  python3 fhspb_standings_patch.py
Резервная копия: post_standings.py.bak_fhspb
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

ANCHOR_FETCH = "    by_group = fetch_standings_by_group(tournament_slug, year_id)\n"
ADD_FETCH = '''    if tournament_slug == PERVENSTVO_SLUG:
        by_group = fhspb_pervenstvo_standings(age, by_group)
'''

ANCHOR_FUNC = "def process_tournament("
ADD_FUNC = '''# ================= Первенство: таблица с fhspb.ru =================
# На fhspb.ru результаты попадают в таблицу сразу после матча, а на
# spb.fhr.ru — с задержкой в дни. Цифры берём с fhspb.ru, логотипы — с
# spb.fhr.ru (там перечислены все команды, даже без сыгранных матчей).
FHSPB_PERVENSTVO = {
    "2009": [(None, 6571)],
    "2010": [(None, 6572)],
    "2011": [("А", 6573), ("Б", 6574)],
    "2012": [("А", 6575), ("Б", 6576)],
    "2013": [("А", 6577), ("Б", 6578)],
    "2014": [("А", 6579), ("Б", 6580)],
    "2015": [("А", 6581), ("Б", 6582)],
}

_FHSPB_TABLE_RE = re.compile(r'<table[^>]*id="StandingsGridView"[^>]*>(.*?)</table>', re.S)
_FHSPB_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_AGE_TAIL_RE = re.compile(r"\\s(?:09|1[0-8])(?=(?:\\s\\d)?$)")


def _cell_text(raw):
    import html as _html
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def _logo_key(name):
    """Ключ для сопоставления логотипов: без регистра, кавычек, ХК/ЖХК,
    дефисов, года/возраста; номер состава сохраняется."""
    t = name.lower().replace("ё", "е")
    t = re.sub(r"[\\"«»]", " ", t)
    t = re.sub(r"\\b(?:19|20)\\d{2}\\b", " ", t)
    t = re.sub(r"\\b(?:09|1[0-8])\\b", " ", t)
    words = [w for w in re.split(r"[\\s\\-]+", t) if w and w not in ("хк", "жхк")]
    return "".join(words)


def _fhspb_display_name(name):
    """'Динамо Питер 11' -> 'Динамо Питер'; 'Красная Машина Юниор 11 2' ->
    'Красная Машина Юниор - 2'."""
    base = _AGE_TAIL_RE.sub("", name).strip()
    m = re.match(r"^(.*\\D)\\s(\\d)$", base)
    return f"{m.group(1)} - {m.group(2)}" if m else base


def _parse_fhspb_table(table_html):
    rows = []
    for tr in re.split(r"<tr[^>]*>", table_html)[1:]:
        cells = [_cell_text(c) for c in _FHSPB_CELL_RE.findall(tr)]
        if len(cells) < 9 or not cells[0].isdigit():
            continue  # заголовок или мусор
        games, wins, draws, losses, _diff, _pen, points = cells[-7:]
        try:
            rows.append({
                "rank": int(cells[0]), "team": cells[1],
                "games": int(games), "wins": int(wins), "losses": int(losses),
                "losses_ot": 0, "losses_so": 0, "points": int(points),
            })
        except ValueError:
            continue
    rows.sort(key=lambda r: r["rank"])
    return rows


def fhspb_pervenstvo_standings(age, spb_by_group):
    """Таблица Первенства с fhspb.ru. При любой проблеме возвращает
    исходные данные spb.fhr.ru (spb_by_group)."""
    config = FHSPB_PERVENSTVO.get(age)
    if not config:
        return spb_by_group
    logos = {}
    for rows in (spb_by_group or {}).values():
        for r in rows:
            if r.get("logo_url"):
                logos[_logo_key(r["team"])] = r["logo_url"]
    result = {}
    try:
        for label, tid in config:
            page = fetch_with_retry(f"https://fhspb.ru/Standings?TournamentID={tid}")
            tables = _FHSPB_TABLE_RE.findall(page)
            rows = _parse_fhspb_table(tables[0]) if tables else []
            for r in rows:
                r["logo_url"] = logos.get(_logo_key(r["team"]))
                r["team"] = _fhspb_display_name(r["team"])
            result[label] = rows
    except Exception as e:
        print(f"[WARN] fhspb.ru: таблица {age} не получена ({e}) — берём spb.fhr.ru")
        return spb_by_group
    if not any(result.values()):
        return spb_by_group
    return result


'''

content = TARGET.read_text(encoding="utf-8")
if "fhspb_pervenstvo_standings" in content:
    print("Уже применено.")
    sys.exit(0)
missing = [n for n, s in (("загрузка таблицы", ANCHOR_FETCH), ("process_tournament", ANCHOR_FUNC)) if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_fhspb"))
content = content.replace(ANCHOR_FUNC, ADD_FUNC + ANCHOR_FUNC, 1)
content = content.replace(ANCHOR_FETCH, ANCHOR_FETCH + ADD_FETCH)
TARGET.write_text(content, encoding="utf-8")
print("Готово: Первенство теперь с fhspb.ru (резервная копия: post_standings.py.bak_fhspb)")
