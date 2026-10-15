#!/usr/bin/env python3
"""
post_schedule.py: на баннере с результатами — вратари (кто реально стоял в
воротах и сколько пропустил) и штрафное время команд, из протокола матча
spb.fhr.ru (spb_protocol.py). Если голы ещё не загружены другим путём —
берутся из протокола.

Протокол каждого сыгранного матча загружается один раз и запоминается
(spb_protocol_cache.json); если в нём голов меньше, чем в счёте, —
перепроверка не чаще раза в 15 минут.

Нужны: spb_protocol.py рядом; spb_all_ages_patch.py уже применён.
Запуск (из ~/vk-bot):  python3 protocol_patch.py
Резервная копия: post_schedule.py.bak_protocol
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

ROW_OLD = '''        g1, g2 = _goals_for_banner(m, spb_lookup)
        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score,
                     "goals1": g1, "goals2": g2})
'''
ROW_NEW = '''        g1, g2 = _goals_for_banner(m, spb_lookup)
        extra = _protocol_extras(m, spb_lookup, score)
        if not g1 and not g2:
            g1, g2 = extra.pop("goals1", []), extra.pop("goals2", [])
        extra.pop("goals1", None), extra.pop("goals2", None)
        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score,
                     "goals1": g1, "goals2": g2, **extra})
'''

FP_OLD = '''    fp = json.dumps(sorted((r["time"] or "", r["team1"], r["team2"], r["score"] or "",
                            r["goals1"], r["goals2"]) for r in rows), ensure_ascii=False)
'''
FP_NEW = '''    fp = json.dumps(sorted((r["time"] or "", r["team1"], r["team2"], r["score"] or "",
                            r["goals1"], r["goals2"], r.get("goalie1", ""), r.get("goalie2", ""),
                            str(r.get("penalty"))) for r in rows), ensure_ascii=False)
'''

FUNC_ANCHOR = "def _goals_for_banner("
FUNC_ADD = '''# ---------- протокол матча: вратари и штрафное время ----------
try:
    import spb_protocol
except Exception as _e:
    print(f"[WARN] spb_protocol.py недоступен ({_e}) — без вратарей и штрафов на баннере")
    spb_protocol = None
PROTOCOL_CACHE_FILE = Path(__file__).parent / "spb_protocol_cache.json"
PROTOCOL_RETRY_SECONDS = 900
_protocol_cache = None
_protocol_session = None


def _protocol_summary(game_id, expected_goals):
    """Сводка протокола матча (из памяти; загрузка — один раз)."""
    global _protocol_cache, _protocol_session
    if spb_protocol is None or spb_fhr_client is None:
        return None
    if _protocol_cache is None:
        try:
            _protocol_cache = json.loads(PROTOCOL_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _protocol_cache = {}
    entry = _protocol_cache.get(str(game_id))
    if entry and (entry.get("complete") or time.time() - entry.get("fetched", 0) < PROTOCOL_RETRY_SECONDS):
        return entry.get("summary")
    try:
        if _protocol_session is None:
            _protocol_session = spb_fhr_client.create_session()
        page = _protocol_session.get(f"https://spb.fhr.ru/games/{game_id}/", timeout=25).text
        summary = spb_protocol.summarize(page)
    except Exception as e:
        print(f"[WARN] Протокол матча {game_id} не получен: {e}")
        return entry.get("summary") if entry else None
    got = len(summary["goals"][1]) + len(summary["goals"][2])
    _protocol_cache[str(game_id)] = {"summary": summary, "fetched": time.time(),
                                     "complete": got >= expected_goals and bool(summary["goalies"][1])}
    PROTOCOL_CACHE_FILE.write_text(json.dumps(_protocol_cache, ensure_ascii=False), encoding="utf-8")
    return summary


def _protocol_extras(m, spb_lookup, score):
    """Вратари, штрафное время и (запасной вариант) голы — для строки баннера."""
    sc = results_banner.split_score(score) if results_banner else None
    sm = (spb_lookup or {}).get(build_match_key(plain_date(m["date"]), m["team1"], m["team2"]))
    if not sc or not sm:
        return {}
    summary = _protocol_summary(sm["game_id"], sc[0] + sc[1])
    if not summary:
        return {}
    import difflib
    def key(name):
        return re.sub(r"[^а-яa-z]", "", re.sub(r"\\b(?:хк|жхк|19\\d\\d|20\\d\\d|\\d\\d)\\b", "",
                                              name.lower().replace("ё", "е")))
    p1 = summary["teams"].get("1") or summary["teams"].get(1) or ""
    same = difflib.SequenceMatcher(None, key(p1), key(m["team1"])).ratio() >= \\
        difflib.SequenceMatcher(None, key(p1), key(m["team2"])).ratio()
    a, b = ("1", "2") if same else ("2", "1")
    get = lambda d, k: d.get(k) if k in d else d.get(int(k), [])

    def goalie_line(entries):
        return ", ".join(f"{who} · {n} проп." for who, n in entries) if entries else ""
    out = {
        "goalie1": goalie_line(get(summary["goalies"], a)),
        "goalie2": goalie_line(get(summary["goalies"], b)),
        "goals1": list(get(summary["goals"], a)),
        "goals2": list(get(summary["goals"], b)),
    }
    if summary.get("penalty"):
        pen = summary["penalty"]
        out["penalty"] = (pen[0], pen[1]) if same else (pen[1], pen[0])
    return out


'''


def main():
    if not (BASE / "spb_protocol.py").exists():
        print("ВНИМАНИЕ: рядом нет spb_protocol.py — сначала скачайте его. Файл НЕ изменён.")
        sys.exit(1)
    content = TARGET.read_text(encoding="utf-8")
    if "def _protocol_extras(" in content:
        print("Уже применено.")
        return
    checks = [("строка баннера", ROW_OLD), ("отпечаток", FP_OLD), ("функция голов", FUNC_ANCHOR)]
    missing = [n for n, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing),
              "— сначала примените spb_all_ages_patch.py. Файл НЕ изменён.")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_protocol"))
    content = content.replace(ROW_OLD, ROW_NEW).replace(FP_OLD, FP_NEW)
    content = content.replace(FUNC_ANCHOR, FUNC_ADD + FUNC_ANCHOR, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("Вратари и штрафное время добавлены на баннер (резервная копия: post_schedule.py.bak_protocol)")


if __name__ == "__main__":
    main()
