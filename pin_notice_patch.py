#!/usr/bin/env python3
"""
VK-бот удаляет из группы служебные сообщения «… закрепил(а) сообщение» —
и после закрепления таблиц ботом, и после закреплений вручную.
Запуск (из ~/vk-bot):  python3 pin_notice_patch.py
"""
import shutil, sys
from pathlib import Path
T = Path(__file__).parent / "vk_to_tg_hockey_bot.py"
OLD = '''        message = update.get("message")
        if not message or message.get("from", {}).get("id") != ADMIN_TELEGRAM_USER_ID:
            continue'''
NEW = '''        message = update.get("message")
        if (message and "pinned_message" in message
                and str(message.get("chat", {}).get("id")) == str(TG_CHANNEL_ID)):
            # служебное «… закрепил(а) сообщение» — убираем из группы
            if delete_telegram_message(message["message_id"]):
                print(f"[OK] Удалено уведомление о закреплении ({message['message_id']})")
            continue
        if not message or message.get("from", {}).get("id") != ADMIN_TELEGRAM_USER_ID:
            continue'''
c = T.read_text(encoding="utf-8")
if "уведомление о закреплении" in c:
    print("vk_to_tg_hockey_bot.py: уже исправлено")
elif c.count(OLD) != 1:
    sys.exit("vk_to_tg_hockey_bot.py: место не найдено — файл НЕ изменён")
else:
    shutil.copy(T, T.with_name("vk_to_tg_hockey_bot.py.bak_pin"))
    T.write_text(c.replace(OLD, NEW, 1), encoding="utf-8")
    print("vk_to_tg_hockey_bot.py: уведомления о закреплении удаляются автоматически")
