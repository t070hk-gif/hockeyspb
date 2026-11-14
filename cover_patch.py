#!/usr/bin/env python3
"""
VK-бот читает обложку видео, когда заголовка не хватило.

Когда: заголовок не совпал ни с одним официальным матчем, совпал неоднозначно
или это анонс без даты. Бот скачивает обложку, распознаёт текст (Tesseract) и
ищет по нему матч: команды, год, дата и время с обложки.
Привязка — только если всё указывает на ОДИН официальный матч; вам в личку
приходит сообщение «🖼 Привязано по обложке» с заголовком и ссылкой.
Каждая обложка распознаётся один раз (кэш cover_ocr_cache.json).
Без tesseract (облако GitHub) — бот работает как раньше.

Нужно: brew install tesseract tesseract-lang
Запуск (из ~/vk-bot):  python3 cover_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "vk_to_tg_hockey_bot.py"

DEF_OLD = '''def _match_video_to_fixture(title: str, upload_ts=None, live_start=None, owner_id=None):
'''
DEF_NEW = '''def _match_video_to_fixture(title: str, upload_ts=None, live_start=None, owner_id=None, video_id=None):
    """Матч по заголовку; не нашёлся — по обложке видео (если передан video_id)."""
    fx, why = _match_video_to_fixture_title(title, upload_ts, live_start, owner_id)
    if fx is not None or not video_id:
        return fx, why
    try:
        alt, alt_why = _match_by_cover(video_id, title, upload_ts, live_start)
    except Exception as e:
        print(f"[WARN] Обложка {video_id} не прочитана: {e}")
        return fx, why
    return (alt, alt_why) if alt else (fx, why)


def _match_by_cover(full_id, title, upload_ts, live_start):
    import cover_ocr
    if not cover_ocr.available() or any(w in (title or "").lower() for w in team_matcher.REVIEW_WORDS):
        return None, ""
    token, _ = get_valid_access_token(load_tokens())
    lines = cover_ocr.read_cover(full_id, token, VK_API_VERSION)
    start_dt = datetime.fromtimestamp(live_start) if live_start else None
    fx, why = cover_ocr.match(lines, team_matcher.match_title, _get_fixtures(),
                              team_matcher.load_alias_groups(),
                              team_matcher.build_date_candidates(title, live_start, upload_ts), start_dt)
    if fx:
        key = f'{fx["key"]}::{fx.get("age") or ""}'
        print(f"[INFO] Видео {full_id} — {why}")
        if cover_ocr.mark_notified(full_id, key):
            send_admin_message(
                f"🖼 Привязано по обложке: {fx['date']} {fx['team1']} — {fx['team2']}"
                f" ({fx.get('age') or '?'} г.р.)\\nЗаголовок: {title}\\n{why}\\n"
                f"https://vk.com/video{full_id}")
    return fx, why


def _match_video_to_fixture_title(title: str, upload_ts=None, live_start=None, owner_id=None):
'''

CALLS = [
    ('''        fx, reason = _match_video_to_fixture(item["title"], item.get("upload_ts"), item.get("live_start"),
                                             owner_id=int(full_id.rsplit("_", 1)[0]))''',
     '''        fx, reason = _match_video_to_fixture(item["title"], item.get("upload_ts"), item.get("live_start"),
                                             owner_id=int(full_id.rsplit("_", 1)[0]), video_id=full_id)'''),
    ('''        fx, reason = _match_video_to_fixture(title, v.get("date"), v.get("live_start_time"),
                                             owner_id=v["owner_id"])''',
     '''        fx, reason = _match_video_to_fixture(title, v.get("date"), v.get("live_start_time"),
                                             owner_id=v["owner_id"], video_id=full_id)'''),
    ('''            fx, fx_reason = _match_video_to_fixture(title, upload_ts, live_start, owner_id=video["owner_id"])''',
     '''            fx, fx_reason = _match_video_to_fixture(title, upload_ts, live_start, owner_id=video["owner_id"],
                                                    video_id=f'{video["owner_id"]}_{video["id"]}')'''),
]

TEST_ADD = r'''

def test_cover_match():
    """Обложка: из распознанного текста выбирается один матч (команды, год, дата, время)."""
    import cover_ocr as c
    import team_matcher as tm
    lines = ["ПЕРВЕНСТВО САНЕТ- ПЕТЕРБУРГА", "BAPATH 14 =X СЕВЕРСТАЛЬ 14", "ПРЯМАЯ ТРАНСЛЯЦИЯ",
             "ВАРЯГИ 14 =x СЕВЕРСТАЛЬ 14", "Череповец", "14.11.2026 ¢ 14:30", "АРЕНА ХОРС e ул. Ладожская 42/1"]
    d = "14.11.2026"
    fx = {d: [{"date": d, "team1": "варяги", "team2": "северсталь", "age": "14", "key": d + "::варяги|северсталь", "time": "14:30"},
              {"date": d, "team1": "варяги", "team2": "северсталь", "age": "10", "key": d + "::варяги|северсталь", "time": "18:00"},
              {"date": d, "team1": "альфа", "team2": "варяги", "age": "14", "key": d + "::альфа|варяги", "time": "10:00"}]}
    r, why = c.match(lines, tm.match_title, fx, [], [])
    assert r and r["age"] == "14" and r["team2"] == "северсталь", why
    r, why = c.match(lines, tm.match_title, {"15.11.2026": fx[d]}, [], [])
    assert r is None, why                          # дата на обложке другая — не привязываем
'''


def main():
    if not (BASE / "cover_ocr.py").exists():
        sys.exit("Нет cover_ocr.py рядом с ботом — положите его в ~/vk-bot. Ничего не изменено")
    c = TARGET.read_text(encoding="utf-8")
    if "def _match_by_cover" in c:
        print("vk_to_tg_hockey_bot.py: уже исправлено")
    else:
        missing = [o[:70] for o, _ in [(DEF_OLD, "")] + CALLS if c.count(o) != 1]
        if missing:
            sys.exit(f"vk_to_tg_hockey_bot.py: НЕ найдено {missing} — файл НЕ изменён")
        shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_cover"))
        c = c.replace(DEF_OLD, DEF_NEW, 1)
        for o, n in CALLS:
            c = c.replace(o, n, 1)
        TARGET.write_text(c, encoding="utf-8")
        print("vk_to_tg_hockey_bot.py: если заголовка не хватило — бот читает обложку видео")
    gi = BASE / ".gitignore"
    if gi.exists() and "cover_ocr_cache.json" not in gi.read_text(encoding="utf-8"):
        gi.write_text(gi.read_text(encoding="utf-8").rstrip("\n") + "\ncover_ocr_cache.json\n", encoding="utf-8")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_cover_match" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест обложек")
    if not shutil.which("tesseract"):
        print("ВНИМАНИЕ: tesseract не найден — установите: brew install tesseract tesseract-lang")


if __name__ == "__main__":
    main()
