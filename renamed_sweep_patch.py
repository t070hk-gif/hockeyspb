#!/usr/bin/env python3
"""
Страховочный обход: видео считается уже привязанным, только если его
заголовок не менялся с момента привязки. Переименовали (например, перенесли
матч на другой день) — видео сопоставляется заново по новому заголовку.
Запуск (из ~/vk-bot):  python3 renamed_sweep_patch.py
"""
import shutil, sys
from pathlib import Path
T = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
ITEMS = [
    ('''    ids = set()
    for k, entry in load_video_index().items():''',
     '''    ids = {}                               # id видео -> заголовки, под которыми его привязали
    for k, entry in load_video_index().items():'''),
    ('''            ids.add(f"{m.group(1)}_{m.group(2)}")''',
     '''            ids.setdefault(f"{m.group(1)}_{m.group(2)}", set()).add((entry.get("title") or "").strip())'''),
    ('''        if full_id in registered:
            continue''',
     '''        titles = registered.get(full_id)
        if titles is not None and ("" in titles or (v.get("title") or "").strip() in titles):
            continue                                  # привязано, заголовок с тех пор не менялся'''),
]
c = T.read_text(encoding="utf-8")
if "заголовок с тех пор не менялся" in c:
    print("vk_to_tg_hockey_bot.py: уже исправлено")
else:
    miss = [o[:50] for o, _ in ITEMS if c.count(o) != 1]
    if miss:
        sys.exit(f"vk_to_tg_hockey_bot.py: НЕ найдено {miss} — файл НЕ изменён")
    shutil.copy(T, T.with_name("vk_to_tg_hockey_bot.py.bak_renamed"))
    for o, n in ITEMS:
        c = c.replace(o, n, 1)
    T.write_text(c, encoding="utf-8")
    print("vk_to_tg_hockey_bot.py: переименованные видео сопоставляются заново")
