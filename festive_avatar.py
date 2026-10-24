#!/usr/bin/env python3
"""
Аватары в стиле «Табло»: обычный и новогодний (шапка Деда Мороза, гирлянда,
снег) — для группы и для бота.

    python3 festive_avatar.py --test    — нарисовать и прислать все аватары в личку
    python3 festive_avatar.py --check   — проверить, может ли бот менять фото группы
    python3 festive_avatar.py --apply   — для cron: с 15.12 ставит новогоднее фото группы,
                                          с 11.01 возвращает обычное (один раз на смену)
Аватар бота Telegram менять ботам не даёт — его ставят вручную: @BotFather → /setuserpic.
"""
import json
import math
import random
import sys
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
from config import TG_BOT_TOKEN, TG_CHAT_ID, ADMIN_ID
import festive

OUT = BASE / "avatars"
STATE = BASE / "avatar_state.json"
N = 1024
FB = str(BASE / "fonts" / "PT_Sans-Web-Bold.ttf")
LED_ON, LED_OFF = (255, 196, 40), (34, 30, 22)
BG, HOUSING, EDGE, RED = (9, 12, 20), (20, 24, 34), (52, 60, 78), (233, 30, 85)
G = {"С": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
     "П": ["11111", "10001", "10001", "10001", "10001", "10001", "10001"],
     "Б": ["11111", "10000", "10000", "11110", "10001", "10001", "11110"]}
HAT = ["......WW.", ".....RRW.", "....RRR..", "...RRRR..", "..RRRRRR.", ".RRRRRRR.", "RRRRRRRRR", "WWWWWWWWW"]
FLAKE = ["1001001", "0101010", "0011100", "1111111", "0011100", "0101010", "1001001"]
BULBS = [(255, 70, 70), (70, 220, 110), (255, 200, 50), (80, 170, 255), (255, 120, 220)]
API = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"


def _f(s):
    return ImageFont.truetype(FB, s)


def _dots(d, rows, x, y, cell, color_of, dot=0.82):
    for r, row in enumerate(rows):
        for c, ch in enumerate(row):
            col = color_of(ch)
            if col:
                d.ellipse([x + c * cell, y + r * cell, x + c * cell + cell * dot, y + r * cell + cell * dot], fill=col)


def _spb(img, cell, y, hat):
    w = cell * 6.4 * 3 - cell * 1.4
    x = (N - w) / 2
    d = ImageDraw.Draw(img)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i, ch in enumerate("СПБ"):
        _dots(d, G[ch], x + i * cell * 6.4, y, cell, lambda b: LED_ON if b == "1" else LED_OFF)
        _dots(gd, G[ch], x + i * cell * 6.4, y, cell, lambda b: (255, 170, 0, 255) if b == "1" else None)
    hc = cell * 0.72                                   # шапка на «С», чуть набекрень
    hx, hy = x - cell * 0.9, y - 7.4 * hc
    if hat:
        _dots(gd, HAT, hx, hy, hc, lambda b: {"R": (255, 40, 40, 170), "W": (255, 255, 255, 150)}.get(b))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(cell * 0.7)))
    d = ImageDraw.Draw(img)
    for i, ch in enumerate("СПБ"):
        _dots(d, G[ch], x + i * cell * 6.4, y, cell, lambda b: LED_ON if b == "1" else None)
    if hat:
        _dots(d, HAT, hx, hy, hc, lambda b: {"R": (235, 40, 50), "W": (245, 248, 255)}.get(b))
    return img


def _garland_snow(img, top, left, right, seed, flakes, frame=None):
    rnd = random.Random(seed)
    d = ImageDraw.Draw(img)
    if frame is None:
        for _ in range(220):
            x, y, r = rnd.randrange(N), rnd.randrange(N), rnd.choice((4, 6, 8))
            d.ellipse([x, y, x + r, y + r], fill=(225, 238, 255, rnd.randrange(40, 130)))
    else:                                              # ролик — снег падает
        img = Image.alpha_composite(img, festive.falling_snow(N, N, frame, 48, seed, count=170, scale=2.2))
        d = ImageDraw.Draw(img)
    glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    wave = lambda x: top + 26 * math.sin((x - left) / (right - left) * math.pi * 3)
    d.line([(x, wave(x)) for x in range(left, right + 1, 6)], fill=(80, 90, 110, 255), width=6)
    for i, x in enumerate(range(left + 20, right - 10, 62)):
        y, col, lv = wave(x), BULBS[i % 5], festive.bulb_level(i, frame, 48)
        lit = tuple(int(30 + (v - 30) * lv) for v in col)
        gd.ellipse([x - 26, y - 6, x + 26, y + 44], fill=col + (int(200 * lv),))
        d.ellipse([x - 13, y + 4, x + 13, y + 34], fill=lit + (255,))
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(18)))
    d = ImageDraw.Draw(img)
    for x, y, c in flakes:
        _dots(d, FLAKE, x, y, c, lambda b: (215, 232, 255, 190) if b == "1" else None)
    return img


def group_avatar(new_year, frame=None):
    img = Image.new("RGBA", (N, N), BG + (255,))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([70, 70, N - 70, N - 70], radius=120, fill=HOUSING, outline=EDGE, width=12)
    if new_year:
        img = _garland_snow(img, 120, 110, N - 110, 3, [(790, 250, 9), (150, 640, 7), (840, 620, 7)], frame)
    img = _spb(img, 40, 420 if new_year else 410, hat=new_year)
    d = ImageDraw.Draw(img)
    t, tf = "ВСЕССЫЛКИ", _f(92 if new_year else 96)
    tw = d.textlength(t, font=tf)
    if new_year:                                       # плашка вниз — сверху место для шапки
        d.rounded_rectangle([(N - tw) / 2 - 40, 730, (N + tw) / 2 + 40, 846], radius=24, fill=RED)
        d.text((N / 2, 788), t, font=tf, fill=(255, 255, 255), anchor="mm")
    else:
        d.rounded_rectangle([(N - tw) / 2 - 40, 190, (N + tw) / 2 + 40, 310], radius=24, fill=RED)
        d.text((N / 2, 250), t, font=tf, fill=(255, 255, 255), anchor="mm")
        d.text((N / 2, 790), "ДЕТСКИЙ ХОККЕЙ", font=_f(66), fill=(150, 160, 180), anchor="mm")
    return img.convert("RGB")


def bot_avatar_ny():
    img = Image.new("RGBA", (N, N), BG + (255,))
    d = ImageDraw.Draw(img)
    d.ellipse([56, 56, N - 56, N - 56], fill=HOUSING, outline=EDGE, width=12)
    img = _garland_snow(img, 175, 200, N - 200, 5, [(770, 300, 8), (180, 640, 6)])
    img = _spb(img, 36, 440, hat=True)
    d = ImageDraw.Draw(img)
    pf = _f(88)
    pw = d.textlength("БОТ", font=pf)
    d.rounded_rectangle([(N - pw) / 2 - 56, 720, (N + pw) / 2 + 56, 844], radius=62, fill=RED)
    d.text((N / 2, 782), "БОТ", font=pf, fill=(255, 255, 255), anchor="mm")
    return img.convert("RGB")


def group_avatar_video(out_mp4, frames=48, fps=12, size=800):
    """Видео-аватар группы: мигающая гирлянда и падающий снег, кольцо 4 секунды."""
    import imageio.v2 as imageio
    import numpy
    with imageio.get_writer(out_mp4, fps=fps, codec="libx264", quality=8, macro_block_size=1,
                            pixelformat="yuv420p") as wr:
        for fr in range(frames):
            wr.append_data(numpy.asarray(group_avatar(True, fr).resize((size, size), Image.LANCZOS)))
    return out_mp4


def render_all():
    OUT.mkdir(exist_ok=True)
    paths = {"group": OUT / "group.png", "group_ny": OUT / "group_ny.png", "bot_ny": OUT / "bot_ny.png"}
    group_avatar(False).save(paths["group"])
    group_avatar(True).save(paths["group_ny"])
    bot_avatar_ny().save(paths["bot_ny"])
    return paths


def main():
    if "--test" in sys.argv:
        p = render_all()
        names = [("group", "Группа — обычный"), ("group_ny", "Группа — новогодний"), ("bot_ny", "Бот — новогодний")]
        media = [{"type": "photo", "media": f"attach://{k}", "caption": t} for k, t in names]
        files = {k: open(p[k], "rb") for k, _ in names}
        r = requests.post(f"{API}/sendMediaGroup", data={"chat_id": ADMIN_ID, "media": json.dumps(media, ensure_ascii=False)},
                          files=files, timeout=60).json()
        print("Отправлено в личку" if r.get("ok") else r)
    elif "--check" in sys.argv:
        me = requests.get(f"{API}/getMe", timeout=20).json()["result"]["id"]
        m = requests.get(f"{API}/getChatMember", params={"chat_id": TG_CHAT_ID, "user_id": me}, timeout=20).json()
        res = m.get("result", {})
        ok = res.get("status") == "creator" or res.get("can_change_info")
        print("✅ Бот может менять фото группы" if ok else
              f"❌ Не может (статус: {res.get('status')}). Дайте боту право «Изменение профиля группы» в настройках администраторов")
    elif "--apply" in sys.argv:
        want = "ny" if festive.in_season() else "normal"
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            state = {"current": "normal"}
        if state.get("current") == want:
            return
        p = render_all()
        with open(p["group_ny" if want == "ny" else "group"], "rb") as fh:
            r = requests.post(f"{API}/setChatPhoto", data={"chat_id": TG_CHAT_ID}, files={"photo": fh}, timeout=60).json()
        if r.get("ok"):
            STATE.write_text(json.dumps({"current": want}), encoding="utf-8")
            print(f"Фото группы: {'новогоднее' if want == 'ny' else 'обычное'}")
            if want == "ny":                       # видео-аватар бот поставить не может — присылаем его админу
                try:
                    mp4 = group_avatar_video(str(OUT / "group_ny.mp4"))
                    with open(mp4, "rb") as fh:
                        requests.post(f"{API}/sendAnimation", files={"animation": fh}, timeout=120, data={
                            "chat_id": ADMIN_ID,
                            "caption": "🎄 Праздники начались: бот поставил новогоднее фото группы. "
                                       "Чтобы гирлянда мигала и шёл снег, загрузите это видео как аватар: "
                                       "группа → Изменить → фото → «Выбрать видео». 11 января бот вернёт обычный аватар."})
                except Exception as e:
                    print("Видео-аватар не отправлен:", e)
        else:
            print("Не удалось сменить фото группы:", r)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
