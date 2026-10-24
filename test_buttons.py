#!/usr/bin/env python3
"""
Тест: пост дня с кнопками-ссылками под картинкой. Присылает в ЛИЧКУ
администратора, канал не трогает.  Запуск (из ~/vk-bot): python3 test_buttons.py
"""
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
from config import TG_BOT_TOKEN, ADMIN_ID

BASE = Path(__file__).parent
image = next(iter(sorted((BASE / "results_images").glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)), None) \
    if (BASE / "results_images").exists() else None
image = image or BASE / "banners" / "2011_groupa_champ.png"

caption = ("<b>СБ 03.10.2026</b>\n\n"
           "📺 СКА 11 - Динамо 11\n📋 Протокол матча\n\n"
           "📺 СКА Серебряные Львы 11 - Динамо Юниор 11\n📋 Протокол матча\n\n"
           "📺 Северсталь 11 - СКА Стрельна 11\n🕐 19:00\n\n"
           "<i>Источники: fhspb.ru, spb.fhr.ru</i>")
video = "https://vk.com/video-210582936_456241222"
protocol = "https://spb.fhr.ru/games/26204694/"
keyboard = {"inline_keyboard": [
    [{"text": "📺 СКА — Динамо", "url": video}, {"text": "📋 Протокол", "url": protocol}],
    [{"text": "📺 СКА СЛ — Динамо Юниор", "url": video}, {"text": "📋 Протокол", "url": protocol}],
    [{"text": "📺 Северсталь — СКА Стрельна", "url": video}],
    [{"text": "🔔 Подписаться", "url": "https://t.me/hockeyjunior_spb"},
     {"text": "↗️ Поделиться", "url": "https://t.me/share/url?url=https://t.me/hockeyjunior_spb"}],
]}
with open(image, "rb") as fh:
    r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                      data={"chat_id": ADMIN_ID, "caption": caption, "parse_mode": "HTML",
                            "reply_markup": json.dumps(keyboard, ensure_ascii=False)},
                      files={"photo": fh}, timeout=30).json()
print("Отправлено в личку — откройте Telegram" if r.get("ok") else r)
