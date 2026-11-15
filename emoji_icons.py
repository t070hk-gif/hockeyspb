#!/usr/bin/env python3
"""
Свои эмодзи для постов (кастомные эмодзи Telegram): значки VK, YouTube, RUTUBE.

Бот создаёт собственный набор эмодзи и вставляет значки в посты.
Условие Telegram (Bot API 9.4): у владельца бота должен быть Telegram Premium.
Если значок не сработал — в посте остаётся обычный эмодзи (📺 / ▶️).

  python3 emoji_icons.py --add rutube ПУТЬ_К_КАРТИНКЕ   — сделать значок из картинки и добавить в набор
  python3 emoji_icons.py --test                         — прислать вам в личку пробное сообщение
  python3 emoji_icons.py --list                         — какие значки есть
Имена значков: vk, youtube, rutube.
"""
import io
import json
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw

BASE = Path(__file__).parent
ICONS_DIR = BASE / "emoji_icons"
MAP_FILE = BASE / "emoji_icons.json"          # {"rutube": "custom_emoji_id", ..., "_ok": true}
FALLBACK = {"vk": "📺", "youtube": "▶️", "rutube": "▶️"}

sys.path.insert(0, str(BASE))
from config import TG_BOT_TOKEN, ADMIN_ID  # noqa: E402

API = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"


def _call(method, data=None, files=None):
    r = requests.post(f"{API}/{method}", data=data, files=files, timeout=60).json()
    if not r.get("ok"):
        raise RuntimeError(f"{method}: {r.get('description')}")
    return r["result"]


def load_map():
    try:
        return json.loads(MAP_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_map(m):
    MAP_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def make_icon(src, out):
    """Картинка → значок 100×100 PNG: обрезка светлой рамки, скруглённые углы, прозрачный фон."""
    im = Image.open(src).convert("RGB")
    w, h = im.size
    side = min(w, h)
    im = im.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    inset = max(1, int(side * 0.004))
    im = im.crop((inset, inset, side - inset, side - inset))
    S = 400
    im = im.resize((S, S), Image.LANCZOS)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.2), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(im, (0, 0), mask)
    icon.resize((100, 100), Image.LANCZOS).save(out, optimize=True)


def set_name():
    return f"vsessylki_icons_by_{_call('getMe')['username']}"


def _ids_in_set(name):
    try:
        return [s["custom_emoji_id"] for s in _call("getStickerSet", {"name": name})["stickers"]]
    except RuntimeError:
        return None


def add(key, src):
    if key not in FALLBACK:
        sys.exit(f"Имя значка — одно из: {', '.join(FALLBACK)}")
    ICONS_DIR.mkdir(exist_ok=True)
    png = ICONS_DIR / f"{key}.png"
    make_icon(src, png)
    name = set_name()
    before = _ids_in_set(name)
    sticker = json.dumps({"sticker": "attach://icon", "format": "static", "emoji_list": [FALLBACK[key]]})
    with open(png, "rb") as f:
        if before is None:
            _call("createNewStickerSet", {"user_id": ADMIN_ID, "name": name, "title": "ВСЕССЫЛКИ.СПБ",
                                          "sticker_type": "custom_emoji", "stickers": f"[{sticker}]"},
                  files={"icon": f})
            before = []
        else:
            _call("addStickerToSet", {"user_id": ADMIN_ID, "name": name, "sticker": sticker}, files={"icon": f})
    new = [i for i in _ids_in_set(name) if i not in before]
    if not new:
        sys.exit("Значок добавлен, но id не получен — запустите --list")
    m = load_map()
    old = m.get(key)
    m[key] = new[-1]
    m.pop("_ok", None)                              # после изменений — проверить заново (--test)
    save_map(m)
    if old and old in _ids_in_set(name):
        try:
            _call("deleteStickerFromSet", {"sticker": _sticker_file_id(name, old)})
        except Exception:
            pass
    print(f"Значок «{key}» готов: {png.name}, id {new[-1]}")
    print(f"Набор: https://t.me/addemoji/{name}")


def _sticker_file_id(name, emoji_id):
    for s in _call("getStickerSet", {"name": name})["stickers"]:
        if s["custom_emoji_id"] == emoji_id:
            return s["file_id"]
    raise RuntimeError("нет в наборе")


def tag(key, fallback=None):
    """HTML для поста: свой значок, если проверен (--test), иначе обычный эмодзи."""
    fb = fallback or FALLBACK.get(key, "")
    m = load_map()
    if m.get("_ok") and m.get(key):
        return f'<tg-emoji emoji-id="{m[key]}">{fb}</tg-emoji>'
    return fb


def test():
    m = load_map()
    keys = [k for k in FALLBACK if m.get(k)]
    if not keys:
        sys.exit("Значков ещё нет — сначала --add")
    text = "Проверка значков: " + " ".join(
        f'<tg-emoji emoji-id="{m[k]}">{FALLBACK[k]}</tg-emoji> {k}' for k in keys)
    msg = _call("sendMessage", {"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML"})
    got = [e for e in msg.get("entities", []) if e.get("type") == "custom_emoji"]
    m["_ok"] = len(got) == len(keys)
    save_map(m)
    if m["_ok"]:
        print("✅ Значки работают — бот будет ставить их в посты")
    else:
        print("❌ Telegram заменил значки обычными эмодзи. Скорее всего, у владельца бота нет Telegram Premium.\n"
              "   В постах останутся обычные эмодзи 📺 ▶️ — ничего не сломается.")


def main():
    if "--add" in sys.argv:
        i = sys.argv.index("--add")
        add(sys.argv[i + 1], sys.argv[i + 2])
    elif "--test" in sys.argv:
        test()
    else:
        m = load_map()
        for k in FALLBACK:
            print(f"  {k}: {m.get(k) or '—'}")
        print("проверено:", "да" if m.get("_ok") else "нет (запустите --test)")


if __name__ == "__main__":
    main()
