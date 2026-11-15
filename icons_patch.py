#!/usr/bin/env python3
"""
post_schedule.py: в постах дня — свои значки VK / YouTube / RUTUBE (emoji_icons.py)
вместо 📺 и ▶️. Пока значки не проверены (--test) — обычные эмодзи, как сейчас.
Запуск (из ~/vk-bot):  python3 icons_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent
T = BASE / "post_schedule.py"
ITEMS = [
('''            team_line = f"📺 <a href=\\"{video_url}\\">{m['team1']} - {m['team2']}</a>"''',
 '''            team_line = f"{_icon('vk', '📺')} <a href=\\"{video_url}\\">{m['team1']} - {m['team2']}</a>"'''),
('''            team_line += f"\\n▶️ <a href=\\"{yt_url}\\">Смотреть на YouTube</a>"''',
 '''            team_line += f"\\n{_icon('youtube', '▶️')} <a href=\\"{yt_url}\\">Смотреть на YouTube</a>"'''),
('''            team_line += f"\\n▶️ <a href=\\"{rt_url}\\">Смотреть на RUTUBE</a>"''',
 '''            team_line += f"\\n{_icon('rutube', '▶️')} <a href=\\"{rt_url}\\">Смотреть на RUTUBE</a>"'''),
('''def _youtube_url(date_label, team1, team2, age, rossii=False, module="youtube_watch"):''',
 '''def _icon(key, fallback):
    """Свой значок площадки (emoji_icons.py) или обычный эмодзи."""
    try:
        import emoji_icons
        return emoji_icons.tag(key, fallback)
    except Exception:
        return fallback


def _youtube_url(date_label, team1, team2, age, rossii=False, module="youtube_watch"):'''),
]
if not (BASE / "emoji_icons.py").exists():
    sys.exit("Нет emoji_icons.py — ничего не изменено")
c = T.read_text(encoding="utf-8")
if "def _icon(" in c:
    print("post_schedule.py: уже исправлено"); sys.exit()
miss = [o[:60] for o, _ in ITEMS if c.count(o) != 1]
if miss:
    sys.exit(f"post_schedule.py: НЕ найдено {miss} — файл НЕ изменён")
shutil.copy(T, T.with_name("post_schedule.py.bak_icons"))
for o, n in ITEMS:
    c = c.replace(o, n, 1)
T.write_text(c, encoding="utf-8")
print("post_schedule.py: значки VK / YouTube / RUTUBE в постах дня")
