#!/usr/bin/env python3
"""
Проверка VK-ключа (сервисного ключа / токена сообщества / пользовательского токена):
какие методы VK API, нужные боту, он пропускает.

    VK_SERVICE_KEY=... python3 check_vk_key.py     # или ключ в config.json (vk_service_key)

Сам ключ нигде не печатается. Код возврата 0 — все методы работают, 1 — есть отказы.
"""
import contextlib
import io
import sys

with contextlib.redirect_stdout(io.StringIO()):
    import vk_to_tg_hockey_bot as bot


def main() -> int:
    try:
        token, _ = bot.get_valid_access_token(bot.load_tokens())
    except SystemExit as e:
        print(f"❌ {e}")
        return 1
    mode = "сервисный ключ / токен сообщества" if bot._vk_service_key() else "пользовательский токен (vk_tokens.json)"
    print(f"Ключ: {mode}")
    group = bot.VK_GROUP_IDS[0]
    checks = [
        ("groups.getById", dict(group_ids=group)),
        ("wall.get", dict(owner_id=-group, count=1)),
        ("video.get (каталог группы)", dict(owner_id=-group, count=1)),
        ("video.get (по списку id)", None),
    ]
    bad = 0
    for name, params in checks:
        method = name.split()[0]
        if params is None:
            with contextlib.redirect_stdout(io.StringIO()):
                videos = bot.vk_get_group_videos(token, group, count=1) or []
            if not videos:
                print(f"–  {name}: пропущено (нет видео для примера)")
                continue
            params = dict(videos=f"{videos[0]['owner_id']}_{videos[0]['id']}")
        with contextlib.redirect_stdout(io.StringIO()):
            data = bot.vk_api(method, token, **params)
        err = data.get("error")
        if err:
            bad += 1
            print(f"❌ {name}: код {err.get('error_code')} — {err.get('error_msg')}")
        else:
            print(f"✅ {name}")
    print("\nВсё работает." if not bad else f"\nОтказов: {bad}. См. раздел «Ключ VK» в README.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
