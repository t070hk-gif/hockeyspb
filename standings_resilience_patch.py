#!/usr/bin/env python3
"""
post_standings.py:
  1. Если сообщение таблицы удалено ("message to edit not found"), таблица
     публикуется заново, закрепляется и запоминается — вместо ошибки на
     каждом прогоне.
  2. Обрыв SSL при соединении с Telegram — до 3 повторов с паузой.
     Повторяется ТОЛЬКО SSL-обрыв при установке соединения (запрос не
     дошёл), чтобы не получить дубль.

Запуск (из ~/vk-bot):  python3 standings_resilience_patch.py
Резервная копия: post_standings.py.bak_resilience
"""
import re
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "post_standings.py"

EDIT_OLD = '                edit_photo(existing["message_id"], image_path, caption=title)\n'
EDIT_NEW = '''                try:
                    edit_photo(existing["message_id"], image_path, caption=title)
                except RuntimeError as e:
                    if "message to edit not found" not in str(e):
                        raise
                    # Сообщение таблицы удалено вручную — публикуем заново.
                    print(f"[INFO] Сообщение {existing['message_id']} удалено — публикую таблицу заново")
                    existing["message_id"] = send_photo(topic_id, image_path, caption=title)
                    pin_message(existing["message_id"])
'''

HELPER_ANCHOR = "def send_photo("
HELPER = '''def _tg_post(url, data=None, files=None, timeout=30):
    """requests.post к Telegram с повтором при SSL-обрыве во время
    соединения (запрос до Telegram не дошёл, повтор безопасен)."""
    last_error = None
    for attempt in range(3):
        if files:
            for f in files.values():
                f.seek(0)
        try:
            return requests.post(url, data=data, files=files, timeout=timeout)
        except requests.exceptions.SSLError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise last_error


'''

content = TARGET.read_text(encoding="utf-8")
if "def _tg_post(" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(EDIT_OLD) != 1 or content.count(HELPER_ANCHOR) != 1:
    print("ВНИМАНИЕ: места не найдены однозначно — файл НЕ изменён")
    sys.exit(1)

content, n = re.subn(r'requests\.post\((\s*)f"https://api\.telegram\.org',
                     r'_tg_post(\1f"https://api.telegram.org', content)
content = content.replace(EDIT_OLD, EDIT_NEW)
content = content.replace(HELPER_ANCHOR, HELPER + HELPER_ANCHOR, 1)

shutil.copy(TARGET, TARGET.with_name("post_standings.py.bak_resilience"))
TARGET.write_text(content, encoding="utf-8")
print(f"Готово: повтор при обрывах ({n} вызовов Telegram), пересоздание удалённой таблицы "
      f"(резервная копия: post_standings.py.bak_resilience)")
