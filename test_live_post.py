#!/usr/bin/env python3
"""
Тест: пост дня в стиле «Табло» во время LIVE-матча, с короткой подписью и
кнопками (▶️ видео, 🔴 LIVE, 📋 протокол). Присылает в ЛИЧКУ администратора.
Запуск (из ~/vk-bot, рядом картинка test_live_banner.png):  python3 test_live_post.py
"""
import json
import sys
from pathlib import Path

import requests

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from config import TG_BOT_TOKEN, ADMIN_ID

image = BASE / "test_live_banner.png"
if not image.exists():
    sys.exit("Нет картинки test_live_banner.png рядом со скриптом — скачайте её и положите в ~/vk-bot")

caption = ("<b>СБ 03.10.2026 · Первенство СПб 2011, группа А</b>\n"
           "🔴 <b>LIVE</b>  СКА СЛ 2:1 Д.Юниор · 2-й период\n"
           "⚡ Гол! 34' Гаврилов (СКА СЛ)\n\n"
           "<i>Источники: fhspb.ru, spb.fhr.ru</i>")
video = "https://vk.com/video-210582936_456241222"
protocol = "https://spb.fhr.ru/games/26204694/"
keyboard = {"inline_keyboard": [
    [{"text": "▶️ СКА — Динамо", "url": video}, {"text": "📋 Протокол", "url": protocol}],
    [{"text": "🔴 LIVE · СКА СЛ — Динамо Юниор", "url": video}],
    [{"text": "▶️ 19:00 · Северсталь — СКА Стрельна", "url": video}],
    [{"text": "🔔 Подписаться", "url": "https://t.me/hockeyjunior_spb"},
     {"text": "↗️ Поделиться", "url": "https://t.me/share/url?url=https://t.me/hockeyjunior_spb"
                                     "&text=%F0%9F%8F%92%20%D0%A0%D0%B5%D0%B7%D1%83%D0%BB%D1%8C%D1%82%D0%B0%D1%82%D1%8B"}],
]}
with open(image, "rb") as fh:
    r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
                      data={"chat_id": ADMIN_ID, "caption": caption, "parse_mode": "HTML",
                            "reply_markup": json.dumps(keyboard, ensure_ascii=False)},
                      files={"photo": fh}, timeout=30).json()
print("Отправлено в личку — откройте Telegram на телефоне" if r.get("ok") else r)
