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


# --- токены не должны попадать в логи (requests пишет полный URL в текст ошибки) ---
import re as _re, sys as _sys
class _RedactStream:
    def __init__(self, stream): self._s = stream
    def write(self, text):
        return self._s.write(_re.sub(r"bot\d+:[\w-]+", "bot***", text) if isinstance(text, str) else text)
    def __getattr__(self, name): return getattr(self._s, name)
if not isinstance(_sys.stdout, _RedactStream):
    _sys.stdout, _sys.stderr = _RedactStream(_sys.stdout), _RedactStream(_sys.stderr)
