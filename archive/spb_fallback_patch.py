#!/usr/bin/env python3
"""
post_schedule.py: запасной источник расписания — spb.fhr.ru.

Если fhspb.ru недоступен (или сработал предохранитель), посты дня на
СЕГОДНЯ и ЗАВТРА строятся по календарю spb.fhr.ru: дата, время, команды,
счёт, ссылка на протокол. Только недостающие посты: уже опубликованные в
это время не трогаются. Ключи постов те же, что от fhspb.ru, поэтому, когда
fhspb.ru вернётся, эти посты продолжат обновляться из основного источника.

Кубок СПб 2010–2015, Кубок Федерации 2016–2018 и Первенство 2009–2015.

Нужен уже применённый spb_all_ages_patch.py.
Запуск (из ~/vk-bot):  python3 spb_fallback_patch.py
Резервная копия: post_schedule.py.bak_fallback
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"

FETCH_OLD = '''    html = fetch_schedule_html(tournament_id, month=month)
    matches = parse_matches(html)
'''
FETCH_NEW = '''    _from_spb = False
    try:
        matches = parse_matches(fetch_schedule_html(tournament_id, month=month))
    except Exception as fhspb_error:
        matches = _spb_fallback_matches(age, group, tournament_type, tournament_id)
        if matches is None:
            raise
        _from_spb = True
        print(f"[INFO] fhspb.ru недоступен — {age} г.р. {group or ''} {tournament_type}: "
              f"посты на сегодня/завтра по данным spb.fhr.ru ({len(matches)} матчей)")
'''

LOOP_OLD = '''    for date_label, day_matches in by_date.items():
        state_key = f"{tournament_id}_{date_label}"
'''
LOOP_NEW = '''    for date_label, day_matches in by_date.items():
        state_key = f"{tournament_id}_{date_label}"
        if _from_spb and state_key in state:
            continue    # запасной источник: опубликованные посты не трогаем, ждём fhspb.ru
'''

FUNC_ANCHOR = "def process_tournament("
FUNC_ADD = '''# ===================== Запасной источник: spb.fhr.ru =====================
_FALLBACK_DAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
_FALLBACK_KEEP_UPPER = {"СКА", "ХКД", "ЖХК", "СШ", "СШОР", "МАХ", "ЦСКА", "ВВС"}


def _spb_display_name(name, age2):
    """'СКА-СЕРЕБРЯНЫЕ ЛЬВЫ' -> 'СКА Серебряные Львы 11';
    'КРАСНАЯ МАШИНА ЮНИОР - 2' -> 'Красная Машина Юниор 11 2' (как на fhspb.ru)."""
    n = re.sub(r'[\\"«»]', " ", name or "")
    n = re.sub(r"(?<![А-ЯЁA-Zа-яёa-z])ХК(?![А-ЯЁA-Zа-яёa-z])", " ", n)
    n = re.sub(r"\\b(?:19|20)\\d{2}\\b", " ", n)
    n = re.sub(r"№\\s*(\\d+)", r"№\\1", n)          # "СШ № 1" -> "СШ №1": номер школы, не состав
    squad = re.search(r"\\s-\\s*(\\d)\\s*$|\\s(\\d)\\s*$", n)
    if squad:
        n = n[:squad.start()]
        squad = squad.group(1) or squad.group(2)
    n = re.sub(r"(?<=\\w)-(?=\\w)", " ", n)
    words = []
    for w in n.split():
        if w in _FALLBACK_KEEP_UPPER or len(w) <= 3 and w.isupper():
            words.append(w)
        elif w.isupper() or w.islower():
            words.append(w.capitalize())
        else:
            words.append(w)
    return " ".join(words) + f" {age2}" + (f" {squad}" if squad else "")


def _spb_calendar_rows(session, tournament_id, slug, year_id, group_id):
    """Календарь Первенства / Кубка Федерации на spb.fhr.ru, со временем матча."""
    import base64, urllib.parse
    group_part = f's:{len(group_id)}:"{group_id}"' if group_id else "N"
    php = (f'a:4:{{s:13:"TOURNAMENT_ID";s:{len(tournament_id)}:"{tournament_id}";s:8:"GROUP_ID";{group_part};'
           f's:7:"YEAR_ID";s:{len(year_id)}:"{year_id}";s:7:"is_ajax";b:1;}}')
    params = urllib.parse.quote(base64.b64encode(php.encode()).decode(), safe="")
    url = (f"https://spb.fhr.ru/fhr-ajax/{spb_fhr_client.AJAX_COMPONENT_PATH}/"
           f"?component=itprofit%3Acompetitions-calendar&template=.default&params={params}")
    referer = f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/"
    text = session.get(url, headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"}, timeout=20).text
    rows = []
    for row in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        gid = spb_fhr_client.ROSSII_GAME_ID_RE.search(row)
        date = spb_fhr_client.ROSSII_DATE_RE.search(row)
        tm = spb_fhr_client.ROSSII_TIME_RE.search(row)
        teams = spb_fhr_client.ROSSII_TEAM_RE.findall(row)
        if not (gid and date and len(teams) >= 2):
            continue
        sc = re.search(r'<div class="cell score[^"]*">\\s*(.*?)\\s*</div>', row, re.S)
        score = re.sub(r"<[^>]+>", "", sc.group(1)).strip() if sc else ""
        rows.append({"game_id": gid.group(1), "date": date.group(1), "time": tm.group(1) if tm else "",
                     "team1": re.sub(r"<[^>]+>", "", teams[0]).strip(),
                     "team2": re.sub(r"<[^>]+>", "", teams[1]).strip(),
                     "score": score if re.search(r"\\d", score) else None,
                     "game_url": f"https://spb.fhr.ru/games/{gid.group(1)}/"})
    return rows


def _spb_fallback_matches(age, group, tournament_type, tournament_id):
    """Матчи на сегодня и завтра со spb.fhr.ru в формате parse_matches();
    None — для этого турнира запасного источника нет."""
    if spb_fhr_client is None:
        return None
    session = spb_fhr_client.create_session()
    src = _spb_extra_source(age, tournament_type)
    if src:
        sp_tid, slug, years = src
        gids = _spb_group_ids(session, slug, years[age]) or [None]
        if tournament_type == "ПЕРВЕНСТВО" and group and len(gids) > 1:
            idx = 0 if group in ("A", "А") else 1
            gids = [gids[idx]] if idx < len(gids) else gids
        raw = []
        for gid in gids:
            raw += _spb_calendar_rows(session, sp_tid, slug, years[age], gid)
    elif tournament_type == "КУБОК" and age in getattr(spb_fhr_client, "KUBOK_SPB_YEAR_IDS", {}):
        raw = spb_fhr_client.fetch_calendar_matches(session, spb_fhr_client.KUBOK_SPB_TOURNAMENT_ID,
                                                    spb_fhr_client.KUBOK_SPB_YEAR_IDS[age])
    else:
        return None

    today, age2 = datetime.now().date(), age[-2:]
    out = []
    for g in raw:
        try:
            d = datetime.strptime(g["date"], "%d.%m.%Y").date()
        except Exception:
            continue
        if not 0 <= (d - today).days <= 1:
            continue
        score = None
        sm = re.match(r"\\s*(\\d+)\\s*:\\s*(\\d+)\\s*(.*)$", g.get("score") or "")
        if sm:
            score = f"{sm.group(1)} : {sm.group(2)}{sm.group(3).strip()}"
        out.append({"date": f"{_FALLBACK_DAYS[d.weekday()]} {g['date']}", "time": g.get("time") or "",
                    "arena": "", "tournament_id": str(tournament_id), "match_id": f"spb{g['game_id']}",
                    "team1": _spb_display_name(g["team1"], age2), "team2": _spb_display_name(g["team2"], age2),
                    "score": score, "protocol_url": g["game_url"]})
    return out


'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "def _spb_fallback_matches(" in content:
        print("Уже применено.")
        return
    if "def _spb_extra_source(" not in content:
        print("ВНИМАНИЕ: сначала примените spb_all_ages_patch.py — файл НЕ изменён")
        sys.exit(1)
    missing = [n for n, s in (("загрузка расписания", FETCH_OLD), ("цикл по дням", LOOP_OLD),
                              ("process_tournament", FUNC_ANCHOR)) if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_fallback"))
    content = content.replace(FETCH_OLD, FETCH_NEW).replace(LOOP_OLD, LOOP_NEW)
    content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("Запасной источник spb.fhr.ru добавлен (резервная копия: post_schedule.py.bak_fallback)")


if __name__ == "__main__":
    main()
