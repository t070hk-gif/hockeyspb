#!/usr/bin/env python3
"""
post_schedule.py: посты праздничных дней (15.12–10.01) — живые картинки:
мигающая гирлянда и падающий снег по шапке. Подписи, ссылки, кнопки и
LIVE-счёт — как обычно. Если ролик не собрался (нет пакетов imageio),
пост уходит праздничной картинкой.

Нужны: festive.py (с falling_snow), применённый festive_patch.py и пакеты
imageio, imageio-ffmpeg, numpy для Python, который запускает бота.
Запуск (из ~/vk-bot):  python3 festive_anim_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

ITEMS = [
    ("сброс признака праздника",
     "    base_banner_path = banner_path\n",
     "    base_banner_path = banner_path\n"
     "    global _FESTIVE_DAY\n"
     "    _FESTIVE_DAY = False\n"),
    ("баннер праздничного дня",
     '''        try:
            import festive
            banner_path = festive.season_banner(base_banner_path, date_label)   # праздники — с гирляндой
        except Exception:
            banner_path = base_banner_path
''',
     '''        try:
            import festive
            # Праздничный день: ролик (гирлянда мигает, снег падает) из обычного баннера;
            # если ролики собрать нельзя — праздничная картинка
            _FESTIVE_DAY = festive.in_season(festive.date_of(date_label)) and festive.can_animate()
            banner_path = base_banner_path if _FESTIVE_DAY else festive.season_banner(base_banner_path, date_label)
        except Exception:
            _FESTIVE_DAY, banner_path = False, base_banner_path
'''),
    ("конец турнира",
     '''                             f"{age} г.р. {group or ''} {tournament_type} — {date_label}", dry_run)


KUBOK_ROSSII_BANNER''',
     '''                             f"{age} г.р. {group or ''} {tournament_type} — {date_label}", dry_run)
    _FESTIVE_DAY = False


KUBOK_ROSSII_BANNER'''),
    ("отправка роликов",
     "def _update_day_post(",
     '''# ===================== Праздничные ролики =====================
_FESTIVE_DAY = False          # текущий пост — праздничный: вместо картинки ролик


def _festive_mp4(image_path):
    """Ролик из готовой картинки: мигающая гирлянда и падающий снег по шапке."""
    import festive
    from PIL import Image as _Img
    src = Path(str(image_path))
    RESULTS_IMAGES_DIR.mkdir(exist_ok=True)
    out = RESULTS_IMAGES_DIR / f"{src.stem}_ny.mp4"
    festive.animate(_Img.open(src), str(out))
    return out


def _send_animation(topic_id, mp4, caption):
    with open(mp4, "rb") as fh:
        data = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendAnimation",
                             data={"chat_id": TG_CHAT_ID, "message_thread_id": topic_id, "caption": caption,
                                   "parse_mode": "HTML", "disable_notification": True},
                             files={"animation": fh}, timeout=60).json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendAnimation error: {data}")
    message_id = data["result"]["message_id"]
    try:
        requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageReplyMarkup",
                      data={"chat_id": TG_CHAT_ID, "message_id": message_id,
                            "reply_markup": _build_share_buttons(topic_id, message_id)}, timeout=30)
    except Exception:
        pass
    return message_id


_send_photo_still = send_photo
_edit_media_still = edit_media


def send_photo(topic_id, banner_path, caption):
    if _FESTIVE_DAY:
        try:
            return _send_animation(topic_id, _festive_mp4(banner_path), caption)
        except Exception as e:
            print(f"[WARN] Праздничный ролик не собрался ({e}) — отправляю картинку")
    return _send_photo_still(topic_id, banner_path, caption)


def edit_media(message_id, image_path, caption, topic_id=None):
    if _FESTIVE_DAY:
        try:
            mp4 = _festive_mp4(image_path)
            media = json.dumps({"type": "animation", "media": "attach://anim", "caption": caption,
                                "parse_mode": "HTML"}, ensure_ascii=False)
            payload = {"chat_id": TG_CHAT_ID, "message_id": message_id, "media": media}
            if topic_id is not None:
                payload["reply_markup"] = _build_share_buttons(topic_id, message_id)
            with open(mp4, "rb") as fh:
                data = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageMedia",
                                     data=payload, files={"anim": fh}, timeout=60).json()
            if data.get("ok") or "message is not modified" in str(data.get("description", "")):
                return
            raise RuntimeError(data)
        except Exception as e:
            print(f"[WARN] Праздничный ролик не обновился ({e}) — обновляю картинкой")
    return _edit_media_still(message_id, image_path, caption, topic_id)


def _update_day_post('''),
]

FESTIVE_ADD = '''

def can_animate():
    """Можно ли собирать ролики (установлены imageio, imageio-ffmpeg, numpy)."""
    try:
        import imageio.v2  # noqa: F401
        import imageio_ffmpeg  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:
        return False
'''

TEST_ADD = '''

def test_festive_animation():
    """Праздничный день: пост уходит роликом (sendAnimation), обычный — картинкой."""
    with quiet():
        import post_schedule as ps
    calls = []

    class R:
        def __init__(self, method):
            self.method = method

        def json(self):
            return {"ok": True, "result": {"message_id": 77}}
    ps.requests.post = lambda url, data=None, files=None, timeout=None: (calls.append(url.rsplit("/", 1)[-1]), R(url))[1]
    ps._festive_mp4 = lambda path: Path(str(path))           # без сборки ролика
    banner = ps.BANNERS_DIR / "2011_groupa_champ.png"
    ps._FESTIVE_DAY = True
    with quiet():
        ps.send_photo(5, banner, "подпись")
    assert calls[0] == "sendAnimation", calls
    calls.clear()
    ps._FESTIVE_DAY = False
    with quiet():
        ps.send_photo(5, banner, "подпись")
    assert calls[0] == "sendPhoto", calls
'''


def main():
    fest = (BASE / "festive.py").read_text(encoding="utf-8")
    if "def falling_snow" not in fest:
        sys.exit("Нужен новый festive.py (с падающим снегом) — ничего не изменено")
    if "def can_animate" not in fest:
        (BASE / "festive.py").write_text(fest.rstrip("\n").replace('\n\nif __name__ == "__main__":', FESTIVE_ADD + '\n\nif __name__ == "__main__":'), encoding="utf-8")
        print("festive.py: добавлена проверка пакетов для роликов")
    content = TARGET.read_text(encoding="utf-8")
    if "_FESTIVE_DAY = False" in content:
        print("post_schedule.py: уже исправлено")
    else:
        missing = [n for n, old, _ in ITEMS if content.count(old) != 1]
        if missing:
            sys.exit(f"post_schedule.py: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён "
                     f"(сначала примените festive_patch.py)")
        shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_festive_anim"))
        for _, old, new in ITEMS:
            content = content.replace(old, new, 1)
        TARGET.write_text(content, encoding="utf-8")
        print("post_schedule.py: посты праздничных дней — ролики с гирляндой и снегом")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_festive_animation" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест праздничных роликов")


if __name__ == "__main__":
    main()
