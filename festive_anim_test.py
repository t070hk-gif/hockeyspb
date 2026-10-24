#!/usr/bin/env python3
"""
Тест мигающей гирлянды: присылает в ЛИЧКУ два ролика —
видео-аватар группы и пост дня с баннером результатов.
Нужен пакет:  python3 -m pip install imageio-ffmpeg
Запуск (из ~/vk-bot):  python3 festive_anim_test.py
"""
import sys
from pathlib import Path

import requests
from PIL import Image

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from config import TG_BOT_TOKEN, ADMIN_ID
import festive
import festive_avatar
import results_banner as rb

out = BASE / "avatars"
out.mkdir(exist_ok=True)
avatar = festive_avatar.group_avatar_video(str(out / "group_ny.mp4"))

plain = BASE / "banners" / "2011_groupa_champ.png"
snowy = plain                      # снег не рисуем — в ролике он падает
M = lambda t, a, b_, s, **k: dict(time=t, team1=a, team2=b_, score=s, **k)
rows = [M("11:00", "СКА 11", "Динамо 11", "5 : 0", goals1=["Еськин 7' (Макавеев)", "Чупарнов 33'"],
          goalie1="Ковалёв · 0 проп.", goalie2="Смирнов · 5 проп.", penalty=(2, 6)),
        M("14:30", "СКА Серебряные Львы 11", "Динамо Юниор 11", "4 : 3ОТ", goals1=["Выскубин 42'"], goals2=["Демин 18'"])]
still = out / "_post.png"
rb.render(snowy, rows, "Вс 27.12.2026", "A", "Первенство СПб 2011 г.р. · группа А", still)
post = festive.animate(Image.open(still), str(out / "post_ny.mp4"))

for path, caption in ((avatar, "Видео-аватар группы (в профиле играет по кругу)"),
                      (post, "❄️ ВС 27.12.2026 ❄️ — пост праздничного дня с мигающей гирляндой")):
    with open(path, "rb") as fh:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendAnimation",
                          data={"chat_id": ADMIN_ID, "caption": caption}, files={"animation": fh}, timeout=120).json()
    print("Отправлено:", Path(path).name if r.get("ok") else r)
