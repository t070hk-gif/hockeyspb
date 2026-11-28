#!/usr/bin/env python3
"""
Одноразовый помощник для получения личного VK-токена через VK ID (PKCE).

УСТАРЕВШИЙ способ: пользовательский токен живёт ~1 час, а refresh_token одноразовый и
может «слететь» (см. README, раздел «Ключ VK»). Бот работает с бессрочным сервисным
ключом (VK_SERVICE_KEY / vk_service_key в config.json) — этот скрипт нужен, только если
сервисный ключ не подошёл.
"""

import base64
import hashlib
import json
import secrets
import sys
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests

CLIENT_ID = "54726270"
REDIRECT_URI = "http://localhost"
SCOPE = "wall,groups,video,offline"
TOKEN_FILE = Path(__file__).parent / "vk_tokens.json"

AUTH_URL = "https://id.vk.ru/authorize"
TOKEN_URL = "https://id.vk.ru/oauth2/auth"


def generate_pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    return verifier, challenge


def main():
    if not CLIENT_ID:
        print("client_id не указан.")
        sys.exit(1)

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_hex(8)

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_link = f"{AUTH_URL}?{urlencode(params)}"

    print("\n1) Откройте эту ссылку в браузере и нажмите «Разрешить»:\n")
    print(auth_link)
    print(
        "\n2) Браузер попытается открыть http://localhost/?code=...\n"
        "   Страница не загрузится — это нормально. Скопируйте ПОЛНЫЙ адрес."
    )

    redirected_url = input("\n3) Вставьте сюда скопированную ссылку: ").strip()

    parsed = urlparse(redirected_url)
    qs = parse_qs(parsed.query)

    if "code" not in qs:
        print(f"\nНе нашёл параметр 'code' в ссылке. Получено: {qs}")
        sys.exit(1)

    code = qs["code"][0]
    device_id = qs.get("device_id", [""])[0]
    returned_state = qs.get("state", [""])[0]

    if returned_state != state:
        print("\n⚠️  ВНИМАНИЕ: state не совпадает с отправленным — прервано в целях безопасности.")
        sys.exit(1)

    token_resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code": code,
            "code_verifier": code_verifier,
            "device_id": device_id,
            "state": state,
        },
        timeout=15,
    )

    print(f"\nОтвет сервера ({token_resp.status_code}):")
    print(token_resp.text)

    if token_resp.status_code == 200:
        data = token_resp.json()
        data["device_id"] = device_id
        TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✅ Токен сохранён в {TOKEN_FILE}")
        if "access_token" in data:
            print(f"\nВаш access_token:\n{data['access_token']}")
        if "refresh_token" in data:
            print("\n(Также сохранён refresh_token для последующего обновления)")
    else:
        print("\n❌ Не удалось получить токен. Проверьте client_id, redirect_uri и scope в настройках приложения.")


if __name__ == "__main__":
    main()
