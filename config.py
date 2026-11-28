"""
Настройки и секреты ботов — читаются из config.json рядом с этим файлом.
config.json в git не хранится (там токен бота); образец — config.example.json.
"""
import json
import os
from pathlib import Path

_PATH = Path(__file__).parent / "config.json"
try:
    _C = json.loads(_PATH.read_text(encoding="utf-8"))
except FileNotFoundError:
    raise SystemExit(f"Нет файла {_PATH}. Скопируйте config.example.json в config.json и заполните.")

TG_BOT_TOKEN = _C["tg_bot_token"]       # токен Telegram-бота
TG_CHAT_ID = int(_C["tg_chat_id"])      # группа ВСЕССЫЛКИ.СПБ
ADMIN_ID = int(_C["admin_id"])          # ваша личка: аварийные уведомления, сводки, ручная привязка видео

# Бессрочный сервисный ключ VK (приложения) или токен сообщества — вместо пользовательского токена.
# Переменная окружения VK_SERVICE_KEY важнее поля vk_service_key в config.json; пусто — старая схема
# (vk_tokens.json + обновление через refresh_token).
def get_vk_service_key() -> str:
    """Ключ читается при каждом вызове: исправленный config.json подхватывается без перезапуска бота."""
    key = os.environ.get("VK_SERVICE_KEY")
    if not key:
        try:
            key = json.loads(_PATH.read_text(encoding="utf-8")).get("vk_service_key")
        except (OSError, ValueError):
            key = _C.get("vk_service_key")
    return str(key or "").strip()


VK_SERVICE_KEY = get_vk_service_key()      # для маскирования в логах

# --- токены не должны попадать в логи (requests пишет полный URL в текст ошибки) ---
import re as _re, sys as _sys
def _redact(text):
    text = _re.sub(r"bot\d+:[\w-]+", "bot***", text)
    text = _re.sub(r"(access_token=)[^&\s'\"]+", r"\1***", text)
    return text.replace(VK_SERVICE_KEY, "***") if len(VK_SERVICE_KEY) >= 8 else text
class _RedactStream:
    def __init__(self, stream): self._s = stream
    def write(self, text):
        return self._s.write(_redact(text) if isinstance(text, str) else text)
    def __getattr__(self, name): return getattr(self._s, name)
if not isinstance(_sys.stdout, _RedactStream):
    _sys.stdout, _sys.stderr = _RedactStream(_sys.stdout), _RedactStream(_sys.stderr)
