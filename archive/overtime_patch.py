#!/usr/bin/env python3
"""
post_schedule.py: пометки «ОТ» / «ПБ» для матчей Первенства.

fhspb.ru не различает победу в основное время, в овертайме и по буллитам.
Для матчей Первенства, завершившихся с разницей в одну шайбу, бот находит
игру в календаре spb.fhr.ru и смотрит число периодов: 4 — «ОТ», 5 — «ПБ».
Ответ запоминается в pervenstvo_ot_cache.json навсегда; если spb.fhr.ru
ещё не внёс игру — повтор не чаще раза в 30 минут на группу.

Запуск (из ~/vk-bot):  python3 overtime_patch.py
Резервная копия: post_schedule.py.bak_ot
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_schedule.py"

CALL_OLD = '''    html = fetch_schedule_html(tournament_id, month=month)
    matches = parse_matches(html)
'''
CALL_NEW = '''    html = fetch_schedule_html(tournament_id, month=month)
    matches = parse_matches(html)
    if tournament_type == "ПЕРВЕНСТВО":
        try:
            _mark_pervenstvo_overtime(age, group, matches)
        except Exception as e:
            print(f"[WARN] Пометки ОТ/ПБ для {age} {group or ''}: {e}")
'''

FUNC_ANCHOR = "def process_tournament("
FUNC_ADD = '''# ================= Первенство: пометки ОТ / ПБ со spb.fhr.ru =================
PERV_OT_CACHE_FILE = Path(__file__).parent / "pervenstvo_ot_cache.json"
PERV_OT_RETRY_SECONDS = 1800
PERV_SPB_TOURNAMENT_ID = "24813508"
PERV_SPB_SLUG = "pervenstvo-spb-24813508"
PERV_SPB_YEAR_IDS = {
    "2009": "24813510", "2010": "24813512", "2011": "24813519", "2012": "24813565",
    "2013": "24813568", "2014": "24813569", "2015": "24813584",
}
_PERV_FILTER_RE = re.compile(r'data-ajax-link="([^"]+)">\\s*Группа\\s*([А-ЯA-Z])\\s*</div>')
_PERV_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_PERV_SCORE_RE = re.compile(r'<div class="cell score[^"]*">\\s*(.*?)\\s*</div>', re.S)
_ONE_GOAL_RE = re.compile(r"^\\s*(\\d+)\\s*:\\s*(\\d+)\\s*$")


def _perv_group_ids(session, year_id):
    """{буква группы: GROUP_ID} из кнопок фильтра на странице года (пусто,
    если турнир не разбит на группы)."""
    import base64, urllib.parse
    url = f"https://spb.fhr.ru/tournaments/{PERV_SPB_SLUG}-year-{year_id}/"
    resp = session.get(url, timeout=20)
    groups = {}
    for link, letter in _PERV_FILTER_RE.findall(resp.text):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(link.replace("&amp;", "&")).query)
        raw = qs.get("params", [""])[0]
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode(errors="ignore")
        m = re.search(r'GROUP_ID";s:\\d+:"(\\d+)"', decoded)
        if m:
            groups[letter] = m.group(1)
    return groups


def _perv_calendar(session, year_id, group_id):
    """Матчи Первенства со spb.fhr.ru: [{game_id, date, team1, team2, score}].
    Разметка строк — как у Кубка России (ссылка на игру в каждой ячейке)."""
    import base64, urllib.parse
    group_part = f's:{len(group_id)}:"{group_id}"' if group_id else "N"
    php = (f'a:4:{{s:13:"TOURNAMENT_ID";s:8:"{PERV_SPB_TOURNAMENT_ID}";s:8:"GROUP_ID";{group_part};'
           f's:7:"YEAR_ID";s:8:"{year_id}";s:7:"is_ajax";b:1;}}')
    params = urllib.parse.quote(base64.b64encode(php.encode()).decode(), safe="")
    url = (f"https://spb.fhr.ru/fhr-ajax/{spb_fhr_client.AJAX_COMPONENT_PATH}/"
           f"?component=itprofit%3Acompetitions-calendar&template=.default&params={params}")
    referer = f"https://spb.fhr.ru/tournaments/{PERV_SPB_SLUG}-year-{year_id}/"
    resp = session.get(url, headers={"Referer": referer, "X-Requested-With": "XMLHttpRequest"}, timeout=20)
    games = []
    for row in _PERV_ROW_RE.findall(resp.text):
        gid = spb_fhr_client.ROSSII_GAME_ID_RE.search(row)
        date = spb_fhr_client.ROSSII_DATE_RE.search(row)
        teams = spb_fhr_client.ROSSII_TEAM_RE.findall(row)
        score = _PERV_SCORE_RE.search(row)
        if gid and date and len(teams) >= 2:
            games.append({"game_id": gid.group(1), "date": date.group(1),
                          "team1": re.sub(r"<[^>]+>", "", teams[0]).strip(),
                          "team2": re.sub(r"<[^>]+>", "", teams[1]).strip(),
                          "score": re.sub(r"<[^>]+>", "", score.group(1)).strip() if score else ""})
    return games


def _mark_pervenstvo_overtime(age, group, matches):
    """Дописывает к счёту матчей Первенства «ОТ» / «ПБ» (на месте, в matches)."""
    todo = []
    for m in matches:
        sc = (m.get("score") or "").strip()
        g = _ONE_GOAL_RE.match(sc)
        if g and abs(int(g.group(1)) - int(g.group(2))) == 1:
            todo.append(m)
    if not todo:
        return

    try:
        cache = json.loads(PERV_OT_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    marks = cache.setdefault("marks", {})
    tries = cache.setdefault("last_try", {})

    def apply(m, suffix):
        if suffix:
            m["score"] = m["score"].strip() + suffix

    pending = []
    for m in todo:
        if m["match_id"] in marks:
            apply(m, marks[m["match_id"]])
        else:
            pending.append(m)

    slot = f"{age}{group or ''}"
    if not pending or spb_fhr_client is None or time.time() - tries.get(slot, 0) < PERV_OT_RETRY_SECONDS:
        return
    tries[slot] = time.time()

    year_id = PERV_SPB_YEAR_IDS.get(age)
    if year_id:
        session = spb_fhr_client.create_session()
        groups = _perv_group_ids(session, year_id)
        letter = {"A": "А", "B": "Б"}.get(group, group)
        group_id = groups.get(letter) if groups else None
        if not groups or group_id:
            lookup = {}
            for gm in _perv_calendar(session, year_id, group_id):
                lookup[build_match_key(gm["date"], gm["team1"], gm["team2"])] = gm
            for m in pending:
                gm = lookup.get(build_match_key(plain_date(m["date"]), m["team1"], m["team2"]))
                if not gm or not gm["score"]:
                    continue    # spb.fhr.ru ещё не внёс игру — попробуем позже
                periods = spb_fhr_client.fetch_match_live_details(session, gm["game_id"]).get("periods", [])
                if len(periods) < 3:
                    continue
                suffix = "ПБ" if len(periods) >= 5 else "ОТ" if len(periods) == 4 else ""
                marks[m["match_id"]] = suffix
                apply(m, suffix)
                if suffix:
                    print(f"[INFO] {m['date']} {m['team1']} — {m['team2']}: {m['score']} (по данным spb.fhr.ru)")
                time.sleep(1)

    PERV_OT_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


'''

content = TARGET.read_text(encoding="utf-8")
if "_mark_pervenstvo_overtime" in content:
    print("Уже применено.")
    sys.exit(0)
missing = [n for n, s in (("загрузка расписания", CALL_OLD), ("process_tournament", FUNC_ANCHOR)) if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_ot"))
content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1).replace(CALL_OLD, CALL_NEW)
TARGET.write_text(content, encoding="utf-8")
print("Пометки ОТ/ПБ для Первенства добавлены (резервная копия: post_schedule.py.bak_ot)")
