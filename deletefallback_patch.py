#!/usr/bin/env python3
"""
Если Telegram не даёт удалить пост (сообщения старше 48 часов бот удалить
не может), бот помечает пост как неактуальный, заменяя подпись.
Уже удалённый пост ("not found") считается успешно удалённым.

Запуск (из ~/vk-bot):  python3 deletefallback_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_deletefallback
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

OLD = '''    if not ok:
        print(f"[WARN] Не удалось удалить пост {message_id}: {resp.text}")
    return ok
'''
NEW = '''    if not ok:
        description = str(data.get("description", ""))
        if "not found" in description:
            print(f"[INFO] Пост {message_id} уже удалён")
            return True
        # Бот не может удалять сообщения старше 48 часов (ограничение
        # Telegram, действует и для администраторов). Редактировать свои
        # сообщения можно без ограничения — помечаем пост как неактуальный.
        try:
            edit = requests.post(
                f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageCaption",
                data={"chat_id": TG_CHANNEL_ID, "message_id": message_id,
                      "caption": "❌ Матч отменён или перенесён"},
                timeout=30,
            ).json()
        except Exception as e:
            edit = {"ok": False, "description": str(e)}
        if edit.get("ok"):
            print(f"[INFO] Пост {message_id} удалить нельзя (старше 48 ч) — помечен как отменённый")
            return True
        print(f"[WARN] Не удалось ни удалить, ни пометить пост {message_id}: "
              f"{resp.text} / {edit.get('description')}")
    return ok
'''

content = TARGET.read_text(encoding="utf-8")
if "editMessageCaption" in content and "помечен как отменённый" in content:
    print("Уже применено.")
    sys.exit(0)
if content.count(OLD) != 1:
    print("ВНИМАНИЕ: место не найдено однозначно, файл НЕ изменён")
    sys.exit(1)
shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_deletefallback"))
TARGET.write_text(content.replace(OLD, NEW), encoding="utf-8")
print("Запасной вариант удаления добавлен (резервная копия: vk_to_tg_hockey_bot.py.bak_deletefallback)")
