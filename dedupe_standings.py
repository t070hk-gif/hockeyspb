#!/usr/bin/env python3
"""
Поиск и удаление дублей турнирных таблиц.

Бот не умеет читать историю группы, поэтому каждое сообщение из диапазона
номеров пересылается администратору в личку, подпись проверяется, а
пересланная копия сразу удаляется. Фото с подписью "Турнирная таблица",
которого нет в standings_state.json, считается дублем.

    python3 dedupe_standings.py                 — показать дубли (номера 1200–1240)
    python3 dedupe_standings.py --apply         — снять закреп и удалить их
    python3 dedupe_standings.py 1140 1240       — другой диапазон номеров
"""
import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, ".")
import post_standings as st

ADMIN_ID = 1158946041
API = f"https://api.telegram.org/bot{st.TG_BOT_TOKEN}"


def call(method, **data):
    try:
        return requests.post(f"{API}/{method}", data=data, timeout=20).json()
    except Exception as e:
        return {"ok": False, "description": str(e)}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    first, last = (int(args[0]), int(args[1])) if len(args) == 2 else (1200, 1240)

    state = json.loads(Path("standings_state.json").read_text(encoding="utf-8"))
    keep = {v["message_id"] for v in state.values()}

    duplicates = []
    for mid in range(first, last + 1):
        r = call("forwardMessage", chat_id=ADMIN_ID, from_chat_id=st.TG_CHAT_ID,
                 message_id=mid, disable_notification=True)
        if not r.get("ok"):
            continue  # удалено, служебное или недоступно
        msg = r["result"]
        call("deleteMessage", chat_id=ADMIN_ID, message_id=msg["message_id"])  # убираем пересланную копию
        caption = msg.get("caption") or ""
        if "photo" in msg and "Турнирная таблица" in caption:
            mark = "оставить" if mid in keep else "ДУБЛЬ"
            print(f"  {mid}: {caption.splitlines()[0][:70]}  — {mark}")
            if mid not in keep:
                duplicates.append(mid)
        time.sleep(0.3)

    print(f"\nДублей найдено: {len(duplicates)} {duplicates}")
    if not duplicates:
        return
    if not apply:
        print("Это только проверка. Для удаления: python3 dedupe_standings.py --apply")
        return

    for mid in duplicates:
        call("unpinChatMessage", chat_id=st.TG_CHAT_ID, message_id=mid)
        r = call("deleteMessage", chat_id=st.TG_CHAT_ID, message_id=mid)
        print(f"  {mid}: {'удалено' if r.get('ok') else r.get('description')}")
        time.sleep(0.3)


if __name__ == "__main__":
    main()
