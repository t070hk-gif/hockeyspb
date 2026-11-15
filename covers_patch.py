#!/usr/bin/env python3
"""
RUTUBE и YouTube: если заголовка не хватило (нет совпадения или неоднозначно —
например, та же пара играла в двух возрастах), бот читает обложку видео
(cover_ocr.py) и ищет матч по ней. Не больше 6 новых обложек за прогон.
Запуск (из ~/vk-bot):  python3 covers_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent

RT = [
('''RECHECK_DAYS = 7
''', '''RECHECK_DAYS = 7
COVERS_PER_RUN = 6                                # не больше обложек за прогон (распознавание ~3 с)
_covers_left = [COVERS_PER_RUN]
'''),
('''        author = (it.get("author") or {}).get("name")
        out.append((vid, it.get("title") or "", _ts(it), url, author))''',
 '''        author = (it.get("author") or {}).get("name")
        out.append((vid, it.get("title") or "", _ts(it), url, author, it.get("thumbnail_url")))'''),
('''def refresh(force=False, verbose=False):
    seen = _read(SEEN_FILE, {})''',
 '''def match_by_cover(image_url, title, dates, ts, fixtures, aliases, cached_lines=None):
    """Не хватило заголовка — читаем обложку (cover_ocr.py). (матч, пояснение, строки обложки)."""
    try:
        import cover_ocr
        import team_matcher as tm
    except Exception:
        return None, "", None
    if not cover_ocr.available() or any(w in title.lower() for w in tm.REVIEW_WORDS):
        return None, "", cached_lines
    lines = cached_lines
    if lines is None:
        if _covers_left[0] <= 0:
            return None, "", None                 # лимит прогона — прочитаем в следующий раз
        _covers_left[0] -= 1
        try:
            lines = cover_ocr.ocr_lines(requests.get(image_url, headers=UA, timeout=30).content)
        except Exception as e:
            print(f"[WARN] обложка не прочитана ({e}): {title}")
            return None, "", None
    fx, why = cover_ocr.match(lines, tm.match_title, fixtures, aliases, dates, datetime.fromtimestamp(ts))
    return fx, why, lines


def refresh(force=False, verbose=False):
    seen = _read(SEEN_FILE, {})'''),
('''    seen["_last_refresh"] = time.time()
    import team_matcher as tm
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    chs = channels()''',
 '''    seen["_last_refresh"] = time.time()
    _covers_left[0] = COVERS_PER_RUN
    import team_matcher as tm
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    chs = channels()'''),
('''        for vid, title, ts, url, _ in items:
            old = seen.get(vid)
            if old and (old.get("key") or time.time() - ts > RECHECK_DAYS * 86400) and old.get("title") == title:
                continue
            fx, why = tm.match_title(title, tm.build_date_candidates(title, ts, None), fixtures=fixtures,
                                     alias_groups=aliases, start_dt=datetime.fromtimestamp(ts))
            item = {"title": title, "ts": ts, "channel": ch.get("name")}''',
 '''        for vid, title, ts, url, _, thumb in items:
            old = seen.get(vid)
            if old and (old.get("key") or time.time() - ts > RECHECK_DAYS * 86400) and old.get("title") == title:
                continue
            dates = tm.build_date_candidates(title, ts, None)
            fx, why = tm.match_title(title, dates, fixtures=fixtures,
                                     alias_groups=aliases, start_dt=datetime.fromtimestamp(ts))
            item = {"title": title, "ts": ts, "channel": ch.get("name")}
            if not fx and thumb:                      # заголовка не хватило — читаем обложку
                fx2, why2, item["cover"] = match_by_cover(thumb, title, dates, ts, fixtures, aliases,
                                                          (old or {}).get("cover"))
                if fx2:
                    fx, why = fx2, why2'''),
]
YT = [
('''            fx, why = match_video(title, ts, fixtures, aliases)
            item = {"title": title, "ts": ts, "channel": ch.get("name")}
''',
 '''            fx, why = match_video(title, ts, fixtures, aliases)
            item = {"title": title, "ts": ts, "channel": ch.get("name")}
            if not fx:                                # заголовка не хватило — читаем обложку
                import rutube_watch as _rw
                fx2, why2, item["cover"] = _rw.match_by_cover(
                    f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", title,
                    tm.build_date_candidates(title, None, ts), ts, fixtures, aliases, (old or {}).get("cover"))
                if fx2:
                    fx, why = fx2, why2
'''),
('''    seen["_last_refresh"] = time.time()
    import team_matcher as tm
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    added = 0''',
 '''    seen["_last_refresh"] = time.time()
    import team_matcher as tm
    try:
        import rutube_watch as _rw
        _rw._covers_left[0] = _rw.COVERS_PER_RUN
    except Exception:
        pass
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    added = 0'''),
]

def patch(name, items):
    t = BASE / name
    c = t.read_text(encoding="utf-8")
    if "заголовка не хватило — читаем обложку" in c:
        print(f"{name}: уже исправлено"); return True
    miss = [o[:50] for o, _ in items if c.count(o) != 1]
    if miss:
        print(f"{name}: НЕ найдено {miss} — файл НЕ изменён"); return False
    shutil.copy(t, t.with_name(name + ".bak_cover"))
    for o, n in items:
        c = c.replace(o, n, 1)
    t.write_text(c, encoding="utf-8")
    print(f"{name}: если заголовка не хватило — читается обложка видео")
    return True

if not (BASE / "cover_ocr.py").exists():
    sys.exit("Нет cover_ocr.py — ничего не изменено")
if patch("rutube_watch.py", RT):
    patch("youtube_watch.py", YT)
