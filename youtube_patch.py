#!/usr/bin/env python3
"""
post_schedule.py: в посте дня под матчем — «▶️ Смотреть на YouTube», если
видео этого матча нашлось на YouTube-канале (youtube_watch.py).
Запуск (из ~/vk-bot):  python3 youtube_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
T = BASE / "post_schedule.py"

ITEMS = [
    ('''        if video_url:
            team_line = f"📺 <a href=\\"{video_url}\\">{m['team1']} - {m['team2']}</a>"
        else:
            team_line = f"📺 {m['team1']} - {m['team2']}"
''',
     '''        if video_url:
            team_line = f"📺 <a href=\\"{video_url}\\">{m['team1']} - {m['team2']}</a>"
        else:
            team_line = f"📺 {m['team1']} - {m['team2']}"
        yt_url = _youtube_url(date_label, m["team1"], m["team2"], age, is_rossii_domain)
        if yt_url:
            team_line += f"\\n▶️ <a href=\\"{yt_url}\\">Смотреть на YouTube</a>"
'''),
    ('''def format_caption(date_label: str, matches: list, video_index: dict,''',
     '''def _youtube_url(date_label, team1, team2, age, rossii=False):
    """Ссылка на видео матча на YouTube (youtube_watch.py) или None."""
    try:
        import youtube_watch
    except Exception:
        return None
    d = plain_date(date_label)
    keys = [build_match_key(d, team1, team2)]
    if rossii:
        keys.insert(0, build_match_key_rossii(d, team1, team2))
    for key in keys:
        url = youtube_watch.url_for(key, age)
        if url:
            return url
    return None


def format_caption(date_label: str, matches: list, video_index: dict,'''),
    ('''    video_index = load_video_index()
''',
     '''    video_index = load_video_index()
    try:                                       # YouTube-каналы: не чаще раза в 10 минут
        import youtube_watch
        youtube_watch.refresh()
    except Exception as e:
        print(f"[WARN] YouTube: {e}")
'''),
]


def main():
    if not (BASE / "youtube_watch.py").exists():
        sys.exit("Нет youtube_watch.py рядом с ботом — ничего не изменено")
    c = T.read_text(encoding="utf-8")
    if "def _youtube_url" in c:
        print("post_schedule.py: уже исправлено")
        return
    miss = [o[:60] for o, _ in ITEMS if c.count(o) != 1]
    if miss:
        sys.exit(f"post_schedule.py: НЕ найдено {miss} — файл НЕ изменён")
    shutil.copy(T, T.with_name("post_schedule.py.bak_youtube"))
    for o, n in ITEMS:
        c = c.replace(o, n, 1)
    T.write_text(c, encoding="utf-8")
    print("post_schedule.py: под матчем — «▶️ Смотреть на YouTube», если видео есть на YouTube")


if __name__ == "__main__":
    main()
