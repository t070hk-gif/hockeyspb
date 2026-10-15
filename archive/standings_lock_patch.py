#!/usr/bin/env python3
"""
post_standings.py:
  1. Блокировка: если прогон уже идёт (cron или ручной), второй сразу
     завершается — иначе оба публикуют одни и те же таблицы (дубли) и
     одновременно пишут одну картинку (IMAGE_PROCESS_FAILED).
  2. Картинка сначала пишется во временный файл и подменяется целиком.

Запуск (из ~/vk-bot):  python3 standings_lock_patch.py
Резервная копия: post_standings.py.bak_lock
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

MAIN_OLD = "def main():\n"
MAIN_NEW = '''def main():
    import fcntl
    lock_file = open(Path(__file__).parent / "post_standings.lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[INFO] Предыдущий прогон ещё выполняется — пропускаем этот запуск.")
        return
'''

SAVE_OLD = "    img.save(out_path)\n"
SAVE_NEW = '''    import os
    tmp_path = f"{out_path}.tmp"
    img.save(tmp_path, format="PNG")
    os.replace(tmp_path, out_path)  # подменяем готовый файл целиком
'''

content = TARGET.read_text(encoding="utf-8")
if "post_standings.lock" in content:
    print("Уже применено.")
    sys.exit(0)
missing = [n for n, s in (("main", MAIN_OLD), ("сохранение картинки", SAVE_OLD)) if content.count(s) != 1]
if missing:
    print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_lock"))
TARGET.write_text(content.replace(MAIN_OLD, MAIN_NEW).replace(SAVE_OLD, SAVE_NEW), encoding="utf-8")
print("Готово (резервная копия: post_standings.py.bak_lock)")
