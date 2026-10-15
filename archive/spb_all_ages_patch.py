#!/usr/bin/env python3
"""
post_schedule.py:
  1. Первенство и Кубок Федерации получают данные spb.fhr.ru, как Кубок СПб:
     ссылки на протоколы, живой счёт и голы во время матча, кэш голов после.
     Календарь запрашивается только при матчах в последние 3 дня / завтра.
  2. На баннере с результатами под каждой командой — её авторы голов
     (фамилия и минута). Если протокол появится позже — баннер перерисуется.

Нужны: results_banner.py (версия с голами) и results_posts_patch.py уже применён.
Запуск (из ~/vk-bot):  python3 spb_all_ages_patch.py
Резервная копия: post_schedule.py.bak_spball
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

RUN_CALL_OLD = '''            process_tournament(age, group, "ПЕРВЕНСТВО", tournament_id, state, video_index, dry_run,
                                official_keys=official_keys)
'''
RUN_CALL_NEW = '''            process_tournament(age, group, "ПЕРВЕНСТВО", tournament_id, state, video_index, dry_run,
                                official_keys=official_keys, spb_session=spb_session,
                                spb_details_cache=spb_details_cache, live_cache=live_cache)
'''

CACHE_OLD = "    spb_details_cache = load_spb_details_cache()\n"
CACHE_NEW = '''    spb_details_cache = load_spb_details_cache()
    globals()["_RESULTS_DETAILS_CACHE"] = spb_details_cache   # голы для баннера с результатами
'''

LOOKUP_OLD = '''        except Exception as e:
            print(f"[WARN] spb.fhr.ru недоступен для {age} г.р. КУБОК: {e}")
'''
LOOKUP_NEW = '''        except Exception as e:
            print(f"[WARN] spb.fhr.ru недоступен для {age} г.р. КУБОК: {e}")
    if (not spb_lookup and spb_session is not None and spb_fhr_client is not None
            and _spb_extra_source(age, tournament_type) and _has_recent_games(matches)):
        try:
            spb_lookup = _spb_lookup_extra(spb_session, age, tournament_type)
        except Exception as e:
            print(f"[WARN] spb.fhr.ru недоступен для {age} г.р. {tournament_type}: {e}")
'''

ROWS_OLD = '''        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score})
    if not any(results_banner.split_score(r["score"]) for r in rows):
        return None, None
    fp = json.dumps(sorted((r["time"] or "", r["team1"], r["team2"], r["score"] or "") for r in rows),
                    ensure_ascii=False)
'''
ROWS_NEW = '''        g1, g2 = _goals_for_banner(m, spb_lookup)
        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score,
                     "goals1": g1, "goals2": g2})
    if not any(results_banner.split_score(r["score"]) for r in rows):
        return None, None
    fp = json.dumps(sorted((r["time"] or "", r["team1"], r["team2"], r["score"] or "",
                            r["goals1"], r["goals2"]) for r in rows), ensure_ascii=False)
'''

FUNC_ANCHOR = "def _results_title("
FUNC_ADD = '''# ---------- spb.fhr.ru для Первенства и Кубка Федерации ----------
SPB_EXTRA_SOURCES = {
    "ПЕРВЕНСТВО": ("24813508", "pervenstvo-spb-24813508", {
        "2009": "24813510", "2010": "24813512", "2011": "24813519", "2012": "24813565",
        "2013": "24813568", "2014": "24813569", "2015": "24813584"}),
    "КУБОК_ФЕДЕРАЦИИ": ("24813588", "kubok-federatsii-spb-24813588", {
        "2016": "24813589", "2017": "24813590", "2018": "24813594"}),
}
SPB_MANUAL_GROUPS = {"24813590": ["25856129", "25856164"]}   # у 2017 кнопок групп на сайте нет
SPB_GROUPS_CACHE_FILE = Path(__file__).parent / "spb_groups_cache.json"
_RESULTS_DETAILS_CACHE = {}
_SPB_GROUP_LINK_RE = re.compile(r'data-ajax-link="([^"]+)">\\s*Группа\\s*[А-ЯA-Z0-9]+\\s*</div>')
_SPB_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_SPB_SCORE_RE = re.compile(r'<div class="cell score[^"]*">\\s*(.*?)\\s*</div>', re.S)


def _spb_extra_source(age, tournament_type):
    if tournament_type == "ПЕРВЕНСТВО":
        src = SPB_EXTRA_SOURCES["ПЕРВЕНСТВО"]
    elif tournament_type == "КУБОК" and age in ("2016", "2017", "2018"):
        src = SPB_EXTRA_SOURCES["КУБОК_ФЕДЕРАЦИИ"]
    else:
        return None
    return src if age in src[2] else None


def _has_recent_games(matches):
    today = datetime.now().date()
    for m in matches:
        try:
            delta = (parse_match_date(m["date"]) - today).days
        except Exception:
            continue
        if -3 <= delta <= 1:
            return True
    return False


def _spb_group_ids(session, slug, year_id):
    """Номера групп года на spb.fhr.ru (запоминаются в файл на весь сезон)."""
    import base64, urllib.parse
    if year_id in SPB_MANUAL_GROUPS:
        return SPB_MANUAL_GROUPS[year_id]
    try:
        cache = json.loads(SPB_GROUPS_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    if year_id in cache:
        return cache[year_id]
    page = session.get(f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/", timeout=20).text
    groups = []
    for link in _SPB_GROUP_LINK_RE.findall(page):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(link.replace("&amp;", "&")).query)
        raw = qs.get("params", [""])[0]
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode(errors="ignore")
        m = re.search(r'GROUP_ID";s:\\d+:"(\\d+)"', decoded)
        if m and m.group(1) not in groups:
            groups.append(m.group(1))
    cache[year_id] = groups
    SPB_GROUPS_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    return groups


def _spb_calendar(session, tournament_id, slug, year_id, group_id):
    import base64, urllib.parse
    group_part = f's:{len(group_id)}:"{group_id}"' if group_id else "N"
    php = (f'a:4:{{s:13:"TOURNAMENT_ID";s:{len(tournament_id)}:"{tournament_id}";s:8:"GROUP_ID";{group_part};'
           f's:7:"YEAR_ID";s:{len(year_id)}:"{year_id}";s:7:"is_ajax";b:1;}}')
    params = urllib.parse.quote(base64.b64encode(php.encode()).decode(), safe="")
    url = (f"https://spb.fhr.ru/fhr-ajax/{spb_fhr_client.AJAX_COMPONENT_PATH}/"
           f"?component=itprofit%3Acompetitions-calendar&template=.default&params={params}")
    referer = f"https://spb.fhr.ru/tournaments/{slug}-year-{year_id}/"
    text = session.get(url, headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"}, timeout=20).text
    games = []
    for row in _SPB_ROW_RE.findall(text):
        gid = spb_fhr_client.ROSSII_GAME_ID_RE.search(row)
        date = spb_fhr_client.ROSSII_DATE_RE.search(row)
        teams = spb_fhr_client.ROSSII_TEAM_RE.findall(row)
        if not (gid and date and len(teams) >= 2):
            continue
        score_m = _SPB_SCORE_RE.search(row)
        score = re.sub(r"<[^>]+>", "", score_m.group(1)).strip() if score_m else ""
        games.append({"game_id": gid.group(1), "date": date.group(1),
                      "team1": re.sub(r"<[^>]+>", "", teams[0]).strip(),
                      "team2": re.sub(r"<[^>]+>", "", teams[1]).strip(),
                      "score": score if re.search(r"\\d", score) else ""})
    return games


def _spb_lookup_extra(session, age, tournament_type):
    tournament_id, slug, years = _spb_extra_source(age, tournament_type)
    year_id = years[age]
    lookup = {}
    for group_id in (_spb_group_ids(session, slug, year_id) or [None]):
        for gm in _spb_calendar(session, tournament_id, slug, year_id, group_id):
            key = build_match_key(gm["date"], gm["team1"], gm["team2"])
            lookup[key] = {"game_id": gm["game_id"], "score": gm["score"],
                           "game_url": f"https://spb.fhr.ru/games/{gm['game_id']}/"}
    return lookup


def _goals_for_banner(m, spb_lookup):
    """Авторы голов каждой команды для баннера: ["Попов 18'", ...] по минутам."""
    sm = (spb_lookup or {}).get(build_match_key(plain_date(m["date"]), m["team1"], m["team2"]))
    breakdown = _RESULTS_DETAILS_CACHE.get(sm["game_id"]) if sm else None
    if not breakdown:
        return [], []
    import difflib
    def key(name):
        return re.sub(r"[^а-яa-z]", "", re.sub(r"\\b(?:хк|жхк|19\\d\\d|20\\d\\d|\\d\\d)\\b", "",
                                              name.lower().replace("ё", "е")))
    k1, k2 = key(m["team1"]), key(m["team2"])
    out = ([], [])
    for period in breakdown:
        for tg in period.get("team_goals", []):
            kt = key(tg.get("name", ""))
            side = 0 if difflib.SequenceMatcher(None, kt, k1).ratio() >= \\
                        difflib.SequenceMatcher(None, kt, k2).ratio() else 1
            for g in tg.get("goals", []):
                try:
                    minute = int(re.match(r"\\d+", str(g.get("minute"))).group(0))
                except Exception:
                    minute = 0
                surname = (g.get("player") or "").split()[0] if g.get("player") else "?"
                out[side].append((minute, f"{surname} {g.get('minute')}'"))
    return [s for _, s in sorted(out[0])], [s for _, s in sorted(out[1])]


'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "def _goals_for_banner(" in content:
        print("Уже применено.")
        return
    if "def _results_image(" not in content:
        print("ВНИМАНИЕ: сначала примените results_posts_patch.py — файл НЕ изменён")
        sys.exit(1)
    rb = (BASE / "results_banner.py").read_text(encoding="utf-8")
    if "_wrap_goals" not in rb:
        print("ВНИМАНИЕ: скачайте новый results_banner.py (с голами) — файл НЕ изменён")
        sys.exit(1)
    checks = [("вызов Первенства", RUN_CALL_OLD), ("кэш голов", CACHE_OLD),
              ("spb.fhr.ru для Кубка", LOOKUP_OLD), ("строки баннера", ROWS_OLD), ("функции", FUNC_ANCHOR)]
    missing = [n for n, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_spball"))
    for old, new in ((RUN_CALL_OLD, RUN_CALL_NEW), (CACHE_OLD, CACHE_NEW), (LOOKUP_OLD, LOOKUP_NEW),
                     (ROWS_OLD, ROWS_NEW)):
        content = content.replace(old, new)
    content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("spb.fhr.ru подключён для всех возрастов, голы на баннере (резервная копия: post_schedule.py.bak_spball)")


if __name__ == "__main__":
    main()
