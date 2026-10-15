#!/usr/bin/env python3
"""
vk_to_tg_hockey_bot.py:
  1. Аварийное уведомление в личку — не чаще раза в час на одну и ту же
     проблему (время отправки хранится в admin_alerts.json, ограничение
     действует и между перезапусками).
  2. При ошибке токена бот не завершается, а раз в минуту перечитывает
     vk_tokens.json: после get_vk_token.py продолжит работу сам.
  3. Перед обновлением токена файл перечитывается: если токен уже обновил
     ручной скрипт, берётся свежий (иначе бот пытался бы использовать
     устаревший одноразовый refresh_token).

Запуск (из ~/vk-bot):  python3 token_alert_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_alert
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

ALERT_OLD = '''    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data={"chat_id": ADMIN_TELEGRAM_USER_ID, "text": f"⚠️ {message}"},
            timeout=15,
        )
    except Exception:
        pass
'''
ALERT_NEW = '''    state_file = Path(__file__).parent / "admin_alerts.json"
    key = message[:60]
    try:
        sent = json.loads(state_file.read_text(encoding="utf-8"))
    except Exception:
        sent = {}
    if time.time() - sent.get(key, 0) < ADMIN_ALERT_INTERVAL:
        return    # такое уведомление уже было меньше часа назад
    try:
        requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            data={"chat_id": ADMIN_TELEGRAM_USER_ID,
                  "text": f"⚠️ {message}\\n\\nБот ждёт новый токен и продолжит работу сам. "
                          f"Повтор этого уведомления — не раньше чем через час."},
            timeout=15,
        )
    except Exception:
        pass
    sent[key] = time.time()
    try:
        state_file.write_text(json.dumps(sent, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
'''

CONST_ANCHOR = "def send_admin_alert(message: str) -> None:\n"
CONST_ADD = "ADMIN_ALERT_INTERVAL = 3600   # одно и то же аварийное уведомление — не чаще раза в час\n\n\n"

TOKENS_OLD = '''    obtained_at = tokens.get("obtained_at", 0)
'''
TOKENS_NEW = '''    # Перечитываем файл: токен мог обновить ручной скрипт или get_vk_token.py.
    try:
        disk = load_tokens()
        if disk.get("refresh_token") and disk.get("refresh_token") != tokens.get("refresh_token"):
            tokens = disk
    except Exception:
        pass
    obtained_at = tokens.get("obtained_at", 0)
'''

MAIN_OLD = '''        except SystemExit as e:
            print(f"[FATAL] {e}")
            break
'''
MAIN_NEW = '''        except SystemExit as e:
            # Ошибка токена: не завершаемся (иначе перезапуск по кругу), а ждём
            # новый токен — файл перечитывается в get_valid_access_token.
            print(f"[FATAL] {e}")
            print("[INFO] Жду новый токен: vk_tokens.json перечитывается раз в минуту")
            time.sleep(60)
            continue
'''


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "ADMIN_ALERT_INTERVAL" in content:
        print("Уже применено.")
        return
    checks = [("уведомление", ALERT_OLD), ("send_admin_alert", CONST_ANCHOR),
              ("обновление токена", TOKENS_OLD), ("главный цикл", MAIN_OLD)]
    missing = [n for n, s in checks if content.count(s) != 1]
    if missing:
        print("ВНИМАНИЕ: не найдено однозначно:", ", ".join(missing), "— файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_alert"))
    content = content.replace(ALERT_OLD, ALERT_NEW).replace(TOKENS_OLD, TOKENS_NEW).replace(MAIN_OLD, MAIN_NEW)
    content = content.replace(CONST_ANCHOR, CONST_ADD + CONST_ANCHOR, 1)
    TARGET.write_text(content, encoding="utf-8")
    print("Готово: уведомления не чаще раза в час, бот ждёт новый токен "
          "(резервная копия: vk_to_tg_hockey_bot.py.bak_alert)")


if __name__ == "__main__":
    main()
