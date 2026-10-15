"""
Настройки и секреты ботов — читаются из config.json рядом с этим файлом.
config.json в git не хранится (там токен бота); образец — config.example.json.
"""
import json
from pathlib import Path

_PATH = Path(__file__).parent / "config.json"
try:
    _C = json.loads(_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    raise SystemExit(f"Нет файла {_PATH}. Скопируйте config.example.json в config.json и заполните.")

TG_BOT_TOKEN = _C["tg_bot_token"]       # токен Telegram-бота
TG_CHAT_ID = int(_C["tg_chat_id"])      # группа ВСЕССЫЛКИ.СПБ
ADMIN_ID = int(_C["admin_id"])          # ваша личка: аварийные уведомления, сводки, ручная привязка видео
