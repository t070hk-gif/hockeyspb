#!/usr/bin/env python3
"""
YouTube-каналы с трансляциями: ищет видео официальных матчей и запоминает
ссылки (youtube_index.json). В посте дня под названием матча появляется
строка «▶️ Смотреть на YouTube». Ссылка на VK в названии — как раньше.

Видео берутся из RSS-ленты каналов (последние 15 видео, без ключа API) и
сопоставляются с расписанием тем же способом, что и видео VK.
Обновляется из post_schedule.py не чаще раза в 10 минут.

  python3 youtube_watch.py                 — обновить и показать найденное
  python3 youtube_watch.py --add ССЫЛКА    — добавить канал (https://www.youtube.com/@имя)
  python3 youtube_watch.py --list          — каналы
"""
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

BASE = Path(__file__).parent
CHANNELS_FILE = BASE / "youtube_channels.json"
INDEX_FILE = BASE / "youtube_index.json"          # "ключ::возраст" -> {url, title}
SEEN_FILE = BASE / "youtube_seen.json"            # id видео -> результат проверки
REFRESH_MIN = 10
RECHECK_DAYS = 7                                  # несопоставленные видео перепроверяем неделю
DEFAULT_CHANNELS = [{"name": "PRO VIDEO", "channel_id": "UCbGF5h1ckLpzcOmGNvOWi2Q"}]
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept-Language": "ru-RU,ru;q=0.9"}


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


def fetch_feed(channel_id):
    """[(id видео, заголовок, время публикации)] из RSS-ленты канала."""
    r = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": channel_id},
                     headers=UA, timeout=20)
    r.raise_for_status()
    out = []
    for e in ET.fromstring(r.content).findall("a:entry", NS):
        vid = e.findtext("yt:videoId", namespaces=NS)
        title = e.findtext("a:title", namespaces=NS) or ""
        pub = e.findtext("a:published", namespaces=NS) or ""
        try:
            ts = datetime.fromisoformat(pub.replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = time.time()
        if vid:
            out.append((vid, title, ts))
    return out


def match_video(title, ts, fixtures=None, aliases=None):
    import team_matcher as tm
    dates = tm.build_date_candidates(title, None, ts)
    return tm.match_title(title, dates, fixtures=fixtures,
                          alias_groups=aliases if aliases is not None else tm.load_alias_groups(),
                          start_dt=None)


def refresh(force=False, verbose=False):
    """Проверяет ленты каналов; новые совпадения записывает в youtube_index.json."""
    seen = _read(SEEN_FILE, {})
    last = seen.get("_last_refresh", 0)
    if not force and time.time() - last < REFRESH_MIN * 60:
        return 0
    seen["_last_refresh"] = time.time()
    import team_matcher as tm
    try:
        import rutube_watch as _rw
        _rw._covers_left[0] = _rw.COVERS_PER_RUN
    except Exception:
        pass
    fixtures, aliases = tm.load_fixtures(), tm.load_alias_groups()
    index = _read(INDEX_FILE, {})
    added = 0
    for ch in channels():
        try:
            feed = fetch_feed(ch["channel_id"])
        except Exception as e:
            print(f"[WARN] YouTube «{ch.get('name')}»: лента недоступна ({e})")
            continue
        for vid, title, ts in feed:
            old = seen.get(vid)
            if old and (old.get("key") or time.time() - ts > RECHECK_DAYS * 86400) and old.get("title") == title:
                continue                               # уже привязано / давно и не подошло
            fx, why = match_video(title, ts, fixtures, aliases)
            item = {"title": title, "ts": ts, "channel": ch.get("name")}
            if not fx:                                # заголовка не хватило — читаем обложку
                import rutube_watch as _rw
                fx2, why2, item["cover"] = _rw.match_by_cover(
                    f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg", title,
                    tm.build_date_candidates(title, None, ts), ts, fixtures, aliases, (old or {}).get("cover"))
                if fx2:
                    fx, why = fx2, why2
            if fx:
                key = f'{fx["key"]}::{fx.get("age") or ""}'
                item["key"] = key
                url = f"https://www.youtube.com/watch?v={vid}"
                if index.get(key, {}).get("url") != url:
                    index[key] = {"url": url, "title": title}
                    added += 1
                    print(f"[OK] YouTube: {fx['date']} {fx['team1']} — {fx['team2']} ({fx.get('age')}) ← {title}")
            elif verbose:
                print(f"[--] YouTube не сопоставлено: {title} — {why}")
            seen[vid] = item
    if len(seen) > 3000:
        for k in sorted((k for k in seen if not k.startswith("_")), key=lambda k: seen[k].get("ts", 0))[:-3000]:
            del seen[k]
    _write(SEEN_FILE, seen)
    if added:
        _write(INDEX_FILE, index)
    return added


_cache = {"mtime": None, "index": {}}


def url_for(key: str, age: str = None):
    """Ссылка YouTube для ключа матча (как в post_schedule) и возраста."""
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


def resolve_channel(link: str):
    """(название, channel_id) по ссылке на канал или видео."""
    m = re.search(r"(UC[\w-]{22})", link)
    if m and "/channel/" in link:
        cid = m.group(1)
    else:
        page = requests.get(link, headers=UA, timeout=20).text
        m = (re.search(r'"(?:externalId|channelId)":"(UC[\w-]{22})"', page)
             or re.search(r"channel_id=(UC[\w-]{22})", page))
        if not m:
            raise SystemExit("Не нашёл id канала на странице — пришлите ссылку вида youtube.com/channel/UC…")
        cid = m.group(1)
    feed = requests.get("https://www.youtube.com/feeds/videos.xml", params={"channel_id": cid}, headers=UA, timeout=20)
    name = ET.fromstring(feed.content).findtext("a:title", namespaces=NS) or cid
    return name, cid


def main():
    if "--add" in sys.argv:
        link = sys.argv[sys.argv.index("--add") + 1]
        name, cid = resolve_channel(link)
        chs = channels()
        if any(c["channel_id"] == cid for c in chs):
            print(f"Канал «{name}» уже есть")
        else:
            chs.append({"name": name, "channel_id": cid})
            _write(CHANNELS_FILE, chs)
            print(f"Добавлен канал «{name}» ({cid})")
        return
    if "--list" in sys.argv:
        for c in channels():
            print(f"  {c['name']}: https://www.youtube.com/channel/{c['channel_id']}")
        return
    n = refresh(force=True, verbose=True)
    print(f"Новых ссылок YouTube: {n}; всего в базе: {len(_read(INDEX_FILE, {}))}")


if __name__ == "__main__":
    main()
