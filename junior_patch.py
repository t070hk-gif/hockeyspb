#!/usr/bin/env python3
"""
Турниры junior.fhr.ru — общим списком (JUNIOR_TOURNAMENTS в post_schedule.py):
  Кубок России (2011 г.р.) — как раньше, ключи постов не меняются;
  «Территория хоккея» до 15 лет (2012 г.р.) и до 14 лет (2013 г.р.) — все игры турнира.
Группы и этапы каждого турнира бот находит сам (раз в 6 часов).

Также: баннеры «Территории хоккея» (бирюзовая плашка) и junior_watch.py —
раз в неделю сообщает в личку о новом турнире junior.fhr.ru с командами СПб.

Запуск (из ~/vk-bot):  python3 junior_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

# ----------------------------------------------------------------- spb_fhr_client.py
CLIENT_ANCHOR = "def fetch_kubok_rossii_matches(session):"
CLIENT_ADD = '''def discover_junior_groups(session, slug, tournament_id):
    """Группы и этапы турнира junior.fhr.ru: {подпись: [YEAR_ID, GROUP_ID]} (раз в 6 часов)."""
    import json as _json
    import re as _re
    from pathlib import Path as _Path
    cache_file = _Path(__file__).parent / "junior_groups.json"
    try:
        cache = _json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        cache = {}
    saved = cache.get(slug) or {}
    if saved.get("groups") and time.time() - saved.get("time", 0) < 6 * 3600:
        return saved["groups"]
    found = {}
    base = f"https://{KUBOK_ROSSII_DOMAIN}/tournaments/{slug}"
    for url in (f"{base}/", f"{base}/calendar/"):
        try:
            page = session.get(url, timeout=25).text
        except Exception:
            continue
        for m in _re.finditer(r'data-ajax-link="([^"]+)"', page):
            p = _rossii_decode_params(m.group(1))
            gid, yid = p.get("GROUP_ID"), p.get("YEAR_ID")
            if not gid or not yid or any(v[1] == gid for v in found.values()):
                continue
            if p.get("TOURNAMENT_ID") and p["TOURNAMENT_ID"] != str(tournament_id):
                continue
            seg = page[m.end(): m.end() + 800]
            nxt = seg.find("data-ajax-link")
            seg = seg[:nxt] if nxt > 0 else seg
            label = next((t.strip() for t in _re.findall(r">([^<]*)<", seg) if t.strip() and len(t.strip()) <= 40), "")
            found[label or f"Группа {len(found) + 1}"] = [yid, gid]
    if found:
        cache[slug] = {"time": time.time(), "groups": found}
        try:
            cache_file.write_text(_json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return found
    return saved.get("groups") or {}


def fetch_junior_matches(session, slug, tournament_id):
    """Все игры турнира junior.fhr.ru по всем группам. Возвращает (матчи, порядок групп)."""
    groups = discover_junior_groups(session, slug, tournament_id)
    games, order = {}, list(groups)
    for label, (year_id, group_id) in groups.items():
        try:
            for m in fetch_calendar_matches(session, tournament_id, year_id, domain=KUBOK_ROSSII_DOMAIN, group_id=group_id) or []:
                m["group"] = label
                games[m.get("game_id") or (m["date"], m["team1"], m["team2"])] = m
        except Exception as e:
            print(f"[WARN] {slug}, {label}: не удалось получить расписание: {e}")
        time.sleep(1.5)
    return list(games.values()), order


'''

# ----------------------------------------------------------------- post_schedule.py
JUNIOR_FUNC = '''JUNIOR_TOURNAMENTS = [
    # key — начало ключа постов; slug None — Кубок России через fetch_kubok_rossii_matches
    {"key": "kubokrossii", "name": "Кубок России", "label": "КУБОК РОССИИ", "age": "2011",
     "slug": None, "banner": "2011_kubokrossii.png"},
    {"key": "territoriya15", "name": "Территория хоккея U15", "label": "ТЕРРИТОРИЯ ХОККЕЯ U15", "age": "2012",
     "slug": "territoriya-khokkeya-u15-26308586", "banner": "2012_territoriya.png"},
    {"key": "territoriya14", "name": "Территория хоккея U14", "label": "ТЕРРИТОРИЯ ХОККЕЯ U14", "age": "2013",
     "slug": "territoriya-khokkeya-u14-26308525", "banner": "2013_territoriya.png"},
]


def process_kubok_rossii(state: dict, dry_run: bool, spb_rossii_session=None,
                          official_keys: set = None, spb_details_cache: dict = None,
                          video_index: dict = None, live_cache: dict = None) -> None:
    """Все турниры junior.fhr.ru из JUNIOR_TOURNAMENTS — по очереди, сбой одного не мешает другим."""
    if spb_fhr_client is None or spb_rossii_session is None:
        return
    for cfg in JUNIOR_TOURNAMENTS:
        try:
            _process_junior(cfg, state, dry_run, spb_rossii_session, official_keys,
                            spb_details_cache, video_index, live_cache)
        except Exception as e:
            print(f"[WARN] {cfg['name']}: {e}")


def _process_junior(cfg, state, dry_run, session, official_keys, spb_details_cache, video_index, live_cache):
    age, name, label = cfg["age"], cfg["name"], cfg["label"]
    topic_id = TOPIC_IDS[age]
    banner = BANNERS_DIR / cfg["banner"]
    try:
        if cfg["slug"] is None:
            junior_matches = spb_fhr_client.fetch_kubok_rossii_matches(session)
            order = list(spb_fhr_client.KUBOK_ROSSII_GROUP_IDS.keys())
        else:
            junior_matches, order = spb_fhr_client.fetch_junior_matches(
                session, cfg["slug"], cfg["slug"].rsplit("-", 1)[1])
    except Exception as e:
        print(f"[WARN] {name} недоступен: {e}")
        return
    if not junior_matches:
        return
    if cfg["slug"] is None:
        # Справочник участников Кубка России — VK-бот ищет по нему видео из групп Кубка России
        teams = sorted({t for rm in junior_matches for t in (rm["team1"], rm["team2"])})
        KUBOK_ROSSII_TEAMS_FILE.write_text(json.dumps(teams, ensure_ascii=False, indent=2), encoding="utf-8")

    matches, spb_lookup = [], {}
    tag = "kubok_rossii" if cfg["key"] == "kubokrossii" else cfg["key"]
    for rm in junior_matches:
        m = {"date": rm["date"], "time": rm["time"], "arena": "", "team1": rm["team1"], "team2": rm["team2"],
             "score": rm["score"], "protocol_url": rm["game_url"], "group_label": rm.get("group")}
        matches.append(m)
        key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
        if official_keys is not None:
            official_keys.add(key)
            _record_official_fixture(key, age, tag, time=m.get("time"))
        spb_lookup[key] = {"game_id": rm["game_id"], "game_url": rm["game_url"], "score": rm["score"]}

    if not banner.exists():
        print(f"[WARN] Баннер не найден: {banner} — пропускаю {name}")
        return

    by_date = {}
    for m in matches:
        by_date.setdefault(m["date"], []).append(m)
    group_order = {g: i for i, g in enumerate(order)}
    for day_matches in by_date.values():
        day_matches.sort(key=lambda m: (group_order.get(m.get("group_label"), 999), m.get("time") or ""))

    for date_label, day_matches in by_date.items():
        state_key = f"{cfg['key']}_{date_label}"
        if live_cache is not None:
            live_cache[state_key] = {"date_label": date_label, "matches": day_matches, "spb_lookup": spb_lookup,
                                     "age": age[-2:], "domain": spb_fhr_client.KUBOK_ROSSII_DOMAIN,
                                     "topic_id": topic_id}
        caption = format_caption(date_label, day_matches, video_index or {}, spb_lookup, session,
                                 spb_details_cache, domain=spb_fhr_client.KUBOK_ROSSII_DOMAIN, age=age[-2:])
        existing = state.get(state_key)
        if existing is None:
            try:
                days_until = (parse_match_date(date_label) - datetime.now().date()).days
            except (ValueError, IndexError):
                days_until = 0
            if days_until > 1:
                continue
            if days_until == 1 and datetime.now().hour < PUBLISH_EVE_HOUR:
                continue
            print(f"\\n[НОВЫЙ ПОСТ] {age} г.р. {label} — {date_label}")
            print(caption)
            if not dry_run:
                img, img_fp = _results_image(state_key, banner, day_matches, spb_lookup, f"{name} {age} г.р.", None)
                message_id = send_photo(topic_id, img or banner, caption)
                state[state_key] = {"message_id": message_id, "caption": caption, "image_fp": img_fp,
                                    "style": globals().get("BANNER_STYLE", "")}
                save_state(state)
                time.sleep(1)
            else:
                print("  (dry-run — не отправлено)")
        else:
            _update_day_post(existing, state, state_key, topic_id, banner, caption, day_matches, spb_lookup,
                             f"{name} {age} г.р.", f"{age} г.р. {label} — {date_label}", dry_run)
'''

# ----------------------------------------------------------------- generate_banner_v3.py
BANNER_EDITS = [
    ('''    "ТОВАРИЩЕСКИЙ": "ТОВАРИЩЕСКИЙ МАТЧ",
}''', '''    "ТОВАРИЩЕСКИЙ": "ТОВАРИЩЕСКИЙ МАТЧ",
    "ТЕРРИТОРИЯ ХОККЕЯ U15": "ТЕРРИТОРИЯ ХОККЕЯ U15",
    "ТЕРРИТОРИЯ ХОККЕЯ U14": "ТЕРРИТОРИЯ ХОККЕЯ U14",
}
TERRITORIYA_TEAL = (0, 150, 136)              # «Территория хоккея» — бирюзовая плашка'''),
    ('''             ROSSII_BLUE if tournament == "КУБОК РОССИИ" else CUP_AMBER)
    ink = (255, 255, 255) if tournament in ("ПЕРВЕНСТВО", "ТОВАРИЩЕСКИЙ", "КУБОК РОССИИ") else (20, 20, 20)''',
     '''             ROSSII_BLUE if tournament == "КУБОК РОССИИ" else
             TERRITORIYA_TEAL if tournament.startswith("ТЕРРИТОРИЯ") else CUP_AMBER)
    ink = (255, 255, 255) if (tournament in ("ПЕРВЕНСТВО", "ТОВАРИЩЕСКИЙ", "КУБОК РОССИИ")
                              or tournament.startswith("ТЕРРИТОРИЯ")) else (20, 20, 20)'''),
    ('''    + [("2011", None, "КУБОК РОССИИ", "2011_kubokrossii.png")]
)''', '''    + [("2011", None, "КУБОК РОССИИ", "2011_kubokrossii.png")]
    + [("2012", None, "ТЕРРИТОРИЯ ХОККЕЯ U15", "2012_territoriya.png"),
       ("2013", None, "ТЕРРИТОРИЯ ХОККЕЯ U14", "2013_territoriya.png")]
)'''),
]

# ----------------------------------------------------------------- junior_watch.py
WATCH = r'''#!/usr/bin/env python3
"""
Раз в неделю: есть ли на junior.fhr.ru турнир с ПРЕДСТОЯЩИМИ матчами команд СПб,
которого бот ещё не ведёт (нет в JUNIOR_TOURNAMENTS). Если есть — сообщение в личку.
О каждом турнире сообщается один раз.      python3 junior_watch.py [--test]
"""
import io
import json
import re
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
import spb_fhr_client as c
with redirect_stdout(io.StringIO()):
    import post_schedule as ps
from config import TG_BOT_TOKEN, ADMIN_ID

STATE = BASE / "junior_watch.json"
SPB = re.compile(r"Санкт-Петербург|СПб|\bСКА\b|Серебрян|Стрельна|Петергоф|Невский|Варяги|Колпино|Армия СКА|ГудГол|"
                 r"Легион|Шайба|Динамо[- ]Юниор|Динамо[- ]Форвард|Динамо[- ]Питер|Красная Машина Юниор", re.I)


def season():
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y}-{y + 1}"


def main():
    s = c.create_session_kubok_rossii()
    base = f"https://{c.KUBOK_ROSSII_DOMAIN}"
    r = s.get(f"{base}/fhr-ajax/SXRwcm9maXRcQXBwXEFqYXhcQWpheFRvdXJuYW1lbnRz/Z2V0VG91cm5hbWVudHNMaXN0/?season={season()}",
              timeout=25, headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/tournaments/"})
    try:
        text = json.dumps(r.json(), ensure_ascii=False).replace("\\/", "/")
    except Exception:
        text = r.text
    known = {t["slug"] for t in ps.JUNIOR_TOURNAMENTS if t["slug"]} | {c.KUBOK_ROSSII_TOURNAMENT_SLUG}
    try:
        notified = set(json.loads(STATE.read_text(encoding="utf-8")))
    except Exception:
        notified = set()
    today = datetime.now().date()
    news = []
    for slug in dict.fromkeys(re.findall(r"/tournaments/([a-z0-9-]+?-\d{6,})/", text)):
        if "-year-" in slug or slug in known or slug in notified:
            continue
        games, _ = c.fetch_junior_matches(s, slug, slug.rsplit("-", 1)[1])
        ahead = [g for g in games if SPB.search(f"{g['team1']} {g['team2']}")
                 and datetime.strptime(g["date"], "%d.%m.%Y").date() >= today]
        if ahead:
            ahead.sort(key=lambda g: datetime.strptime(g["date"], "%d.%m.%Y"))
            news.append((slug, len(ahead), ahead[0]))
    for slug, n, g in news:
        text = (f"🆕 На junior.fhr.ru турнир с играми команд СПб, который бот не ведёт:\n{base}/tournaments/{slug}/\n"
                f"Предстоит матчей с командами СПб: {n}, ближайший {g['date']}: {g['team1']} — {g['team2']}.\n"
                f"Чтобы подключить — добавьте его в JUNIOR_TOURNAMENTS (post_schedule.py).")
        print(text)
        if "--test" not in sys.argv:
            requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                          data={"chat_id": ADMIN_ID, "text": text}, timeout=20)
            notified.add(slug)
    STATE.write_text(json.dumps(sorted(notified)), encoding="utf-8")
    print(f"Проверено: новых турниров с командами СПб — {len(news)}")


if __name__ == "__main__":
    main()
'''

TEST_ADD = '''

def test_junior_tournaments():
    """Турниры junior.fhr.ru списком: у каждого свой ключ постов, баннер и тема."""
    with quiet():
        import post_schedule as ps
    keys = [t["key"] for t in ps.JUNIOR_TOURNAMENTS]
    assert len(keys) == len(set(keys)) and "kubokrossii" in keys
    for t in ps.JUNIOR_TOURNAMENTS:
        assert t["age"] in ps.TOPIC_IDS, t
    import generate_banner_v3 as gb
    from PIL import Image
    img = gb.make_banner("2012", None, "ТЕРРИТОРИЯ ХОККЕЯ U15")
    assert img.size == (1200, 260)
'''


def replace_first_function(content, name, new_code):
    start = content.index(f"def {name}(")
    pos = content.index("\n", start) + 1
    while pos < len(content):
        end = content.find("\n", pos)
        end = len(content) if end == -1 else end
        line = content[pos:end]
        if line.strip() and not line[0].isspace():
            break
        pos = end + 1
    return content[:start] + new_code.rstrip("\n") + "\n\n\n" + content[pos:]


def main():
    cl = BASE / "spb_fhr_client.py"
    c = cl.read_text(encoding="utf-8")
    if "def fetch_junior_matches" not in c:
        if "def _rossii_decode_params" not in c or c.count(CLIENT_ANCHOR) != 1:
            sys.exit("spb_fhr_client.py: нужен применённый rossii_groups_patch.py — ничего не изменено")
        shutil.copy(cl, cl.with_name("spb_fhr_client.py.bak_junior"))
        cl.write_text(c.replace(CLIENT_ANCHOR, CLIENT_ADD + CLIENT_ANCHOR, 1), encoding="utf-8")
        print("spb_fhr_client.py: сбор игр любого турнира junior.fhr.ru")
    ps = BASE / "post_schedule.py"
    c = ps.read_text(encoding="utf-8")
    if "JUNIOR_TOURNAMENTS" not in c:
        if c.count("def process_kubok_rossii(") != 1:
            sys.exit("post_schedule.py: функция Кубка России не найдена — ничего не изменено")
        shutil.copy(ps, ps.with_name("post_schedule.py.bak_junior"))
        ps.write_text(replace_first_function(c, "process_kubok_rossii", JUNIOR_FUNC), encoding="utf-8")
        print("post_schedule.py: турниры junior.fhr.ru списком (Кубок России + «Территория хоккея» U15, U14)")
    gb = BASE / "generate_banner_v3.py"
    c = gb.read_text(encoding="utf-8")
    if "TERRITORIYA_TEAL" not in c:
        missing = [o[:40] for o, _ in BANNER_EDITS if c.count(o) != 1]
        if missing:
            sys.exit(f"generate_banner_v3.py: не найдено {missing} — нужна версия с плашкой Кубка России")
        for o, n in BANNER_EDITS:
            c = c.replace(o, n)
        gb.write_text(c, encoding="utf-8")
        print("generate_banner_v3.py: баннеры «Территории хоккея» (бирюзовая плашка)")
    (BASE / "junior_watch.py").write_text(WATCH, encoding="utf-8")
    print("junior_watch.py: еженедельная проверка новых турниров")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_junior_tournaments" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест турниров junior.fhr.ru")


if __name__ == "__main__":
    main()
