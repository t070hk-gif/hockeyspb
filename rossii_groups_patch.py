#!/usr/bin/env python3
"""
spb_fhr_client.py: Кубок России — бот сам находит ВСЕ группы и этапы турнира
на сайте (раз в 6 часов) и берёт игры из всех: «Группа A-II», «Стыковые…»
и любые следующие этапы подхватываются без правки настроек. Если сайт не
ответил — используются группы из прошлого раза или из настроек.

Запуск (из ~/vk-bot):  python3 rossii_groups_patch.py
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "spb_fhr_client.py"

OLD = '''def fetch_kubok_rossii_matches(session):
    all_matches = []
    for group_name, group_id in KUBOK_ROSSII_GROUP_IDS.items():'''
NEW = '''def _rossii_decode_params(link):
    """Параметры кнопки фильтра (TOURNAMENT_ID, GROUP_ID, YEAR_ID). Без html.unescape:
    он портит «&params=», принимая «&para» за символ «¶»."""
    import re as _re
    text = link
    while "&amp;" in text:
        text = text.replace("&amp;", "&")
    m = _re.search(r"params=([^&\\"'\\s]+)", text)
    if not m:
        return {}
    raw = urllib.parse.unquote(m.group(1))
    try:
        dec = base64.b64decode(raw + "=" * (-len(raw) % 4)).decode(errors="ignore")
    except Exception:
        return {}
    return dict(_re.findall(r's:\\d+:"([A-Z_]+)";s:\\d+:"(\\d*)"', dec))


def discover_kubok_rossii_groups(session):
    """Все группы и этапы Кубка России со страницы турнира — {подпись: GROUP_ID}.
    Раз в 6 часов; если сайт не ответил — прошлый результат или группы из настроек."""
    import json as _json
    import re as _re
    from pathlib import Path as _Path
    cache = _Path(__file__).parent / "kubok_rossii_groups.json"
    try:
        saved = _json.loads(cache.read_text(encoding="utf-8"))
    except Exception:
        saved = {}
    if saved.get("groups") and time.time() - saved.get("time", 0) < 6 * 3600:
        return saved["groups"]
    found = {}
    base = f"https://{KUBOK_ROSSII_DOMAIN}/tournaments/{KUBOK_ROSSII_TOURNAMENT_SLUG}"
    for url in (f"{base}-year-{KUBOK_ROSSII_YEAR_ID}/", f"{base}/", f"{base}/calendar/"):
        try:
            page = session.get(url, timeout=25).text
        except Exception:
            continue
        for m in _re.finditer(r'data-ajax-link="([^"]+)"', page):
            p = _rossii_decode_params(m.group(1))
            gid = p.get("GROUP_ID")
            if not gid or gid in found.values():
                continue
            if p.get("TOURNAMENT_ID") and p["TOURNAMENT_ID"] != str(KUBOK_ROSSII_TOURNAMENT_ID):
                continue
            seg = page[m.end(): m.end() + 800]
            nxt = seg.find("data-ajax-link")
            seg = seg[:nxt] if nxt > 0 else seg
            label = next((t.strip() for t in _re.findall(r">([^<]*)<", seg) if t.strip() and len(t.strip()) <= 40), "")
            found[label or f"Группа {len(found) + 1}"] = gid
    if found:
        try:
            cache.write_text(_json.dumps({"time": time.time(), "groups": found}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        return found
    return saved.get("groups") or dict(KUBOK_ROSSII_GROUP_IDS)


def fetch_kubok_rossii_matches(session):
    all_matches = []
    groups = discover_kubok_rossii_groups(session)
    KUBOK_ROSSII_GROUP_IDS.clear()
    KUBOK_ROSSII_GROUP_IDS.update(groups)                # порядок групп в посте — как на сайте
    for group_name, group_id in KUBOK_ROSSII_GROUP_IDS.items():'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "def discover_kubok_rossii_groups" in content:
        print("spb_fhr_client.py: уже исправлено")
        return
    if content.count(OLD) != 1:
        sys.exit("spb_fhr_client.py: место не найдено — файл НЕ изменён")
    shutil.copy(TARGET, TARGET.with_name("spb_fhr_client.py.bak_rossii"))
    TARGET.write_text(content.replace(OLD, NEW), encoding="utf-8")
    print("spb_fhr_client.py: Кубок России — бот сам находит все группы и этапы")


if __name__ == "__main__":
    main()
