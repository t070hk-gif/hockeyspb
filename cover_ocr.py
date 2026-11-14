#!/usr/bin/env python3
"""
Чтение обложки видео VK (Tesseract) — запасной способ найти матч, когда
заголовок не помог: не совпал ни с одним матчем, неоднозначен или анонс без даты.

Из текста обложки берутся строки с командами («ВАРЯГИ 14 =x СЕВЕРСТАЛЬ 14»),
дата и время («14.11.2026 • 14:30»). Привязка — только если все варианты
указывают на ОДИН официальный матч.

Нет tesseract (например, в облаке GitHub) — модуль молча ничего не делает.
Ручная проверка:  python3 cover_ocr.py -27313226_456240426
"""
import io
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).parent
CACHE_FILE = BASE / "cover_ocr_cache.json"
RECHECK_HOURS = 6          # не чаще: проверить, не сменили ли обложку
CACHE_MAX = 3000

_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](20\d{2})(?!\d)")
_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3])[:.]([0-5]\d)(?![\d.])")
_WORD_RE = re.compile(r"[А-ЯЁа-яё]{3,}")
# разделители команд на обложках: «=x», «х», «×», «vs», «:» между словами
_SEP_RE = re.compile(r"\s(?:=\s*)?[xXхХ×](?=\s)|\s=(?=\s)|\s+vs\.?\s+|\s[—–]\s", re.I)


def available() -> bool:
    return shutil.which("tesseract") is not None


def _load():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(cache):
    if len(cache) > CACHE_MAX:
        for k in sorted(cache, key=lambda k: cache[k].get("checked", 0))[:-CACHE_MAX]:
            del cache[k]
    tmp = CACHE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CACHE_FILE)


def cover_url(full_id: str, token: str, api_version: str = "5.199"):
    r = requests.get("https://api.vk.com/method/video.get", timeout=20,
                     params={"videos": full_id, "access_token": token, "v": api_version}).json()
    items = (r.get("response") or {}).get("items") or []
    images = items[0].get("image") or [] if items else []
    return max(images, key=lambda i: i.get("width", 0))["url"] if images else None


def _tesseract(path, *extra):
    p = subprocess.run(["tesseract", str(path), "-", "-l", "rus+eng", *extra],
                       capture_output=True, timeout=60)
    return p.stdout.decode("utf-8", "replace")


def ocr_lines(image_bytes: bytes) -> list:
    """Два прохода: как есть и увеличенная контрастная копия с поиском надписей по всей картинке."""
    from PIL import Image, ImageOps
    import tempfile
    lines = []
    with tempfile.TemporaryDirectory() as d:
        raw = Path(d) / "c.png"
        big = Path(d) / "b.png"
        im = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        im.save(raw)
        g = im.convert("L")
        ImageOps.autocontrast(g.resize((g.width * 2, g.height * 2))).save(big)
        for text in (_tesseract(raw), _tesseract(big, "--psm", "11")):
            for line in text.splitlines():
                line = " ".join(line.split())
                if line and line not in lines:
                    lines.append(line)
    return lines


def read_cover(full_id: str, token: str, api_version: str = "5.199") -> list:
    """Строки текста с обложки (с кэшем: распознаётся один раз на каждую обложку)."""
    cache = _load()
    item = cache.get(full_id) or {}
    now = time.time()
    if item and now - item.get("checked", 0) < RECHECK_HOURS * 3600:
        return item.get("lines", [])
    url = cover_url(full_id, token, api_version)
    if not url:
        return []
    base_url = url.split("?")[0]
    if item.get("url") != base_url:
        data = requests.get(url, timeout=30).content
        item = {"url": base_url, "lines": ocr_lines(data), "notified": item.get("notified")}
    item["checked"] = now
    cache[full_id] = item
    _save(cache)
    return item["lines"]


def mark_notified(full_id: str, key: str) -> bool:
    """True — если про эту привязку ещё не сообщали (и запоминает, что сообщили)."""
    cache = _load()
    item = cache.setdefault(full_id, {})
    if item.get("notified") == key:
        return False
    item["notified"] = key
    _save(cache)
    return True


def dates_in(lines) -> list:
    out = []
    for line in lines:
        for d, m, y in _DATE_RE.findall(line):
            if 1 <= int(d) <= 31 and 1 <= int(m) <= 12:
                s = f"{int(d):02d}.{int(m):02d}.{y}"
                if s not in out:
                    out.append(s)
    return out


def time_in(lines):
    for line in lines:
        if _DATE_RE.search(line):
            m = _TIME_RE.search(_DATE_RE.sub(" ", line))
            if m:
                return f"{int(m.group(1)):02d}:{m.group(2)}"
    return None


def _clean(line: str) -> str:
    line = _DATE_RE.sub(" ", line)
    return " ".join(_SEP_RE.sub(" - ", f" {line} ").split())


def candidates(lines) -> list:
    """Строки, где могут быть команды; и пары соседних строк (команды бывают на разных строках)."""
    good = [_clean(l) for l in lines if len(_WORD_RE.findall(l)) >= 1 and len(l) >= 5]
    out = list(dict.fromkeys(good))
    for a, b in zip(good, good[1:]):
        if " - " not in a and " - " not in b:
            out.append(f"{a} - {b}")
    return out


def match(lines, match_title, fixtures, alias_groups, fallback_dates, start_dt=None):
    """(матч | None, пояснение). Матч — только если все варианты с обложки указывают на один."""
    if not lines:
        return None, "на обложке нет текста"
    dates = dates_in(lines) or list(fallback_dates or [])
    if not dates:
        return None, "на обложке нет даты, и других дат нет"
    hm = time_in(lines)
    if hm and dates_in(lines):
        from datetime import datetime
        try:
            start_dt = datetime.strptime(f"{dates[0]} {hm}", "%d.%m.%Y %H:%M")
        except ValueError:
            pass
    found = {}
    for cand in candidates(lines):
        fx, _ = match_title(cand + (f" {hm}" if hm else ""), dates, fixtures=fixtures,
                            alias_groups=alias_groups, start_dt=start_dt)
        if fx:
            found[(fx["key"], fx.get("age"))] = (fx, cand)
    if not found:
        return None, "по обложке матч не найден"
    if len(found) > 1:
        return None, "по обложке несколько матчей: " + "; ".join(c for _, c in found.values())
    fx, cand = next(iter(found.values()))
    return fx, f"по обложке: «{cand}»" + (f", {dates[0]} {hm}" if hm else "")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("python3 cover_ocr.py -OWNER_ID")
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        import vk_to_tg_hockey_bot as bot
    import team_matcher
    full_id = sys.argv[1].replace("video", "")
    token, _ = bot.get_valid_access_token(bot.load_tokens())
    _load_cache = _load()
    _load_cache.pop(full_id, None)
    _save(_load_cache)
    lines = read_cover(full_id, token, bot.VK_API_VERSION)
    print("Текст с обложки:\n  " + "\n  ".join(lines) if lines else "Текста нет")
    print("Дата:", dates_in(lines), "время:", time_in(lines))
    print("Кандидаты:\n  " + "\n  ".join(candidates(lines)))
    fx, why = match(lines, team_matcher.match_title, bot._get_fixtures(),
                    team_matcher.load_alias_groups(), [])
    print("Итог:", (f"{fx['date']} {fx['team1']} — {fx['team2']} ({fx.get('age') or '?'})" if fx else "нет"), "—", why)
