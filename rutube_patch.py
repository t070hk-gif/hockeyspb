#!/usr/bin/env python3
"""
post_schedule.py: под матчем — «▶️ Смотреть на RUTUBE», если видео нашлось
на RUTUBE-канале (rutube_watch.py). Нужен применённый youtube_patch.py.
Запуск (из ~/vk-bot):  python3 rutube_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent
T = BASE / "post_schedule.py"
ITEMS = [
    ('''        if yt_url:
            team_line += f"\\n▶️ <a href=\\"{yt_url}\\">Смотреть на YouTube</a>"
''',
     '''        if yt_url:
            team_line += f"\\n▶️ <a href=\\"{yt_url}\\">Смотреть на YouTube</a>"
        rt_url = _youtube_url(date_label, m["team1"], m["team2"], age, is_rossii_domain, "rutube_watch")
        if rt_url:
            team_line += f"\\n▶️ <a href=\\"{rt_url}\\">Смотреть на RUTUBE</a>"
'''),
    ('''def _youtube_url(date_label, team1, team2, age, rossii=False):
    """Ссылка на видео матча на YouTube (youtube_watch.py) или None."""
    try:
        import youtube_watch
    except Exception:
        return None''',
     '''def _youtube_url(date_label, team1, team2, age, rossii=False, module="youtube_watch"):
    """Ссылка на видео матча на YouTube / RUTUBE (youtube_watch.py, rutube_watch.py) или None."""
    try:
        import importlib
        youtube_watch = importlib.import_module(module)
    except Exception:
        return None'''),
    ('''        import youtube_watch
        youtube_watch.refresh()
    except Exception as e:
        print(f"[WARN] YouTube: {e}")
''',
     '''        import youtube_watch
        youtube_watch.refresh()
    except Exception as e:
        print(f"[WARN] YouTube: {e}")
    try:                                       # RUTUBE-каналы: так же, не чаще раза в 10 минут
        import rutube_watch
        rutube_watch.refresh()
    except Exception as e:
        print(f"[WARN] RUTUBE: {e}")
'''),
]
if not (BASE / "rutube_watch.py").exists():
    sys.exit("Нет rutube_watch.py рядом с ботом — ничего не изменено")
c = T.read_text(encoding="utf-8")
if "Смотреть на RUTUBE" in c:
    print("post_schedule.py: уже исправлено")
    sys.exit()
if "def _youtube_url" not in c:
    sys.exit("Сначала примените youtube_patch.py — ничего не изменено")
miss = [o[:60] for o, _ in ITEMS if c.count(o) != 1]
if miss:
    sys.exit(f"post_schedule.py: НЕ найдено {miss} — файл НЕ изменён")
shutil.copy(T, T.with_name("post_schedule.py.bak_rutube"))
for o, n in ITEMS:
    c = c.replace(o, n, 1)
T.write_text(c, encoding="utf-8")
print("post_schedule.py: под матчем — «▶️ Смотреть на RUTUBE», если видео есть на RUTUBE")
