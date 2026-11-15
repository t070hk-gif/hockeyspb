#!/usr/bin/env python3
"""
RUTUBE-каналы с трансляциями — как youtube_watch.py: находит видео
официальных матчей и запоминает ссылки (rutube_index.json); в посте дня
под матчем появляется строка «▶️ Смотреть на RUTUBE».

Видео берутся из открытого API RUTUBE (последние 20 видео канала).
Обновляется из post_schedule.py не чаще раза в 10 минут.

  python3 rutube_watch.py                 — обновить и показать найденное
  python3 rutube_watch.py --add ССЫЛКА    — добавить канал (https://rutube.ru/channel/НОМЕР/)
  python3 rutube_watch.py --list          — каналы
"""
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).parent
CHANNELS_FILE = BASE / "rutube_channels.json"
INDEX_FILE = BASE / "rutube_index.json"           # "ключ::возраст" -> {url, title}
SEEN_FILE = BASE / "rutube_seen.json"
REFRESH_MIN = 10
RECHECK_DAYS = 7
COVERS_PER_RUN = 6                                # не больше обложек за прогон (распознавание ~3 с)
_covers_left = [COVERS_PER_RUN]
DEFAULT_CHANNELS = [{"name": "Swan'S", "id": "24817889"}, {"name": "канал 44836015", "id": "44836015"},
                    {"name": "канал 75184074", "id": "75184074"}]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json"}


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write(path, data):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def channels():
    if not CHANNELS_FILE.exists():
        _write(CHANNELS_FILE, DEFAULT_CHANNELS)
    return _read(CHANNELS_FILE, DEFAULT_CHANNELS)


def _ts(item):
    for f in ("created_ts", "publication_ts", "last_update_ts"):
        v = item.get(f)
        if v:
            try:
                return datetime.fromisoformat(str(v).replace("Z", "")).timestamp()
            except ValueError:
                pass
    return time.time()


def fetch_channel(channel_id):
    """[(id видео, заголовок, время, ссылка, автор)] — последние видео канала."""
    r = requests.get(f"https://rutube.ru/api/video/person/{channel_id}/",
                     params={"page": 1, "format": "json"}, headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    for it in r.json().get("results", []):
        vid = str(it.get("id") or "")
        if not vid:
            continue
        url = it.get("video_url") or f"https://rutube.ru/video/{vid}/"
        author = (it.get("author") or {}).get("name")
        out.append((vid, it.get("title") or "", _ts(it), url, author, it.get("thumbnail_url")))
    return out


def match_by_cover(image_url, title, dates, ts, fixtures, aliases, cached_lines=None):
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
    fx, why = cover_ocr.match(lines, tm.match_title, fixtures, aliases, dates, datetime.fromtimestamp(ts), title=title)
    return fx, why, lines


def refresh(force=False, verbose=False):
    seen = _read(SEEN_FILE, {})
    if not force and time.time() - seen.get("_last_refresh", 0) < REFRESH_MIN * 60:
        return 0
    seen["_last_refresh"] = time.time()
    _covers_left[0] = COVERS_PER_RUN
    import team_matcher as tm
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    chs = channels()
    renamed = False
    added = 0
    for ch in chs:
        try:
            items = fetch_channel(ch["id"])
        except Exception as e:
            print(f"[WARN] RUTUBE «{ch.get('name')}»: канал недоступен ({e})")
            continue
        if items and items[0][4] and ch.get("name", "").startswith("канал "):
            ch["name"], renamed = items[0][4], True
        for vid, title, ts, url, _, thumb in items:
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
                    fx, why = fx2, why2
            if fx:
                key = f'{fx["key"]}::{fx.get("age") or ""}'
                item["key"] = key
                if index.get(key, {}).get("url") != url:
                    index[key] = {"url": url, "title": title}
                    added += 1
                    print(f"[OK] RUTUBE: {fx['date']} {fx['team1']} — {fx['team2']} ({fx.get('age')}) ← {title}")
            elif verbose:
                print(f"[--] RUTUBE не сопоставлено: {title} — {why}")
            seen[vid] = item
    if renamed:
        _write(CHANNELS_FILE, chs)
    if len(seen) > 3000:
        for k in sorted((k for k in seen if not k.startswith("_")), key=lambda k: seen[k].get("ts", 0))[:-3000]:
            del seen[k]
    _write(SEEN_FILE, seen)
    if added:
        _write(INDEX_FILE, index)
    return added


_cache = {"mtime": None, "index": {}}


def url_for(key: str, age: str = None):
    try:
        mtime = INDEX_FILE.stat().st_mtime
    except OSError:
        return None
    if _cache["mtime"] != mtime:
        _cache.update(mtime=mtime, index=_read(INDEX_FILE, {}))
    idx = _cache["index"]
    age2 = str(age)[-2:] if age else ""
    if age2 and f"{key}::{age2}" in idx:
        return idx[f"{key}::{age2}"]["url"]
    if not age2:
        hits = [v["url"] for k, v in idx.items() if k.rsplit("::", 1)[0] == key]
        if len(hits) == 1:
            return hits[0]
    return None


def main():
    if "--add" in sys.argv:
        link = sys.argv[sys.argv.index("--add") + 1]
        m = re.search(r"/channel/(\d+)", link) or re.fullmatch(r"(\d+)", link.strip())
        if not m:
            raise SystemExit("Нужна ссылка вида https://rutube.ru/channel/НОМЕР/")
        cid = m.group(1)
        chs = channels()
        if any(c["id"] == cid for c in chs):
            print("Канал уже есть")
            return
        items = fetch_channel(cid)
        name = (items[0][4] if items else None) or f"канал {cid}"
        chs.append({"name": name, "id": cid})
        _write(CHANNELS_FILE, chs)
        print(f"Добавлен канал «{name}» ({cid}), видео в ленте: {len(items)}")
        return
    if "--list" in sys.argv:
        for c in channels():
            print(f"  {c['name']}: https://rutube.ru/channel/{c['id']}/")
        return
    n = refresh(force=True, verbose=True)
    print(f"Новых ссылок RUTUBE: {n}; всего в базе: {len(_read(INDEX_FILE, {}))}")


if __name__ == "__main__":
    main()
