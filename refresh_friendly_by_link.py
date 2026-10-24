#!/usr/bin/env python3
"""
Новый баннер «Табло» для товарищеских постов, которых нет в памяти бота — по ссылкам.
Подпись (со ссылками) берётся из самого поста, год рождения — из подписи.

    python3 refresh_friendly_by_link.py ССЫЛКА [ССЫЛКА ...]           — показать (без изменений)
    python3 refresh_friendly_by_link.py --apply ССЫЛКА [ССЫЛКА ...]   — заменить картинки
"""
import io, json, re, sys, time
from contextlib import redirect_stdout
from pathlib import Path
import requests
sys.path.insert(0, str(Path(__file__).parent))
with redirect_stdout(io.StringIO()):
    import vk_to_tg_hockey_bot as bot

API = f"https://api.telegram.org/bot{bot.TG_BOT_TOKEN}"
apply_ = "--apply" in sys.argv
links = [a for a in sys.argv[1:] if a.startswith("http")]
for link in links:
    mid = int(link.rstrip("/").split("/")[-1])
    fw = requests.post(f"{API}/forwardMessage", data={"chat_id": bot.ADMIN_TELEGRAM_USER_ID,
                       "from_chat_id": bot.TG_CHANNEL_ID, "message_id": mid}, timeout=30).json()
    if not fw.get("ok"):
        print(f"{link}: не удалось прочитать пост — {fw.get('description')}")
        continue
    msg = fw["result"]
    requests.post(f"{API}/deleteMessage", data={"chat_id": bot.ADMIN_TELEGRAM_USER_ID, "message_id": msg["message_id"]}, timeout=30)
    caption, entities = msg.get("caption", ""), msg.get("caption_entities", [])
    m = re.search(r"\b20(09|1[0-8])\b", caption) or re.search(r"\b(09|1[0-8])\b", caption)
    age = m.group(1) if m else None
    banner = bot.get_friendly_banner_path(age)
    print(f"{link}: год {('20' + age) if age else 'не определён'} → {banner.name} | {caption[:70].replace(chr(10), ' | ')}")
    if not apply_:
        continue
    media = {"type": "photo", "media": "attach://p", "caption": caption, "caption_entities": entities}
    with open(banner, "rb") as fh:
        r = requests.post(f"{API}/editMessageMedia", data={"chat_id": bot.TG_CHANNEL_ID, "message_id": mid,
                          "media": json.dumps(media, ensure_ascii=False)}, files={"p": fh}, timeout=60).json()
    print("   обновлён ✓" if r.get("ok") else f"   ошибка: {r.get('description')}")
    time.sleep(3)
