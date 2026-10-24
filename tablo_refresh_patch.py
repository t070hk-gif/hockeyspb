#!/usr/bin/env python3
"""
Перевод всех постов дня на стиль «Табло».

У каждого поста запоминается стиль его картинки (style). Если он не
совпадает с текущим BANNER_STYLE, бот один раз заменяет картинку: где есть
результаты — баннер с результатами, где матчи впереди — баннер турнира.
Подписи не меняются. Лимит — RESULTS_EDITS_PER_RUN замен за прогон.
В будущем для смены стиля достаточно поменять BANNER_STYLE.

Запуск (из ~/vk-bot):  python3 tablo_refresh_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

ITEMS = [
    ("константа стиля",
     "RESULTS_EDITS_PER_RUN = 15\n",
     "RESULTS_EDITS_PER_RUN = 15\n"
     "BANNER_STYLE = \"tablo\"     # стиль картинок; пост в другом стиле перерисуется один раз\n"),
    ("проверка стиля",
     '''    image_changed = img_fp != existing.get("image_fp")
    caption_changed = existing.get("caption") != caption''',
     '''    image_changed = img_fp != existing.get("image_fp") or existing.get("style") != BANNER_STYLE
    caption_changed = existing.get("caption") != caption'''),
    ("запоминание стиля",
     '''        edit_media(existing["message_id"], img or banner_path, caption, topic_id)
        existing["image_fp"] = img_fp''',
     '''        edit_media(existing["message_id"], img or banner_path, caption, topic_id)
        existing["image_fp"] = img_fp
        existing["style"] = BANNER_STYLE'''),
    ("стиль нового поста",
     '''                    "caption": caption,
                    "image_fp": img_fp,
                }''',
     '''                    "caption": caption,
                    "image_fp": img_fp,
                    "style": BANNER_STYLE,
                }'''),
]


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "BANNER_STYLE" in content:
        print("post_schedule.py: уже исправлено")
        return
    missing = [n for n, old, _ in ITEMS if content.count(old) != 1]
    if missing:
        sys.exit(f"post_schedule.py: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
    shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_refresh"))
    for _, old, new in ITEMS:
        content = content.replace(old, new)
    TARGET.write_text(content, encoding="utf-8")
    print("post_schedule.py: все посты будут переведены на стиль «Табло» (по 15 за прогон)")


if __name__ == "__main__":
    main()
