#!/usr/bin/env python3
"""
Бот турнирных таблиц: тянет турнирную таблицу с spb.fhr.ru и публикует/
обновляет один пост в соответствующей теме Telegram-группы.

Таблица оформлена как СГЕНЕРИРОВАННОЕ ИЗОБРЕЖЕНИЕ (Pillow), а не текст/
inline-кнопки — после экспериментов с inline-кнопками выяснилось, что
Telegram делит ширину кнопок в ряду ПОРОВНУ независимо от содержимого, и
это не настраивается программно, из-за чего длинные названия команд
обрезались до нескольких букв. Изображение даёт полный контроль над
раскладкой колонок.

Часть турниров (например, Кубок Федерации) делит команды на НЕСКОЛЬКО
групп — каждая группа подгружается ОТДЕЛЬНЫМ AJAX-запросом (см.
_build_ajax_url). Часть турниров показывает одну таблицу сразу на
странице.

РЕЖИМЫ ЗАПУСКА:
    python3 post_standings.py --dry-run
    python3 post_standings.py --live
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from config import TG_BOT_TOKEN  # секреты — в config.json
from config import TG_CHAT_ID

STATE_FILE = Path(__file__).parent / "standings_state.json"
IMAGES_DIR = Path(__file__).parent / "standings_images"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TOPIC_IDS = {
    "2009": 3, "2010": 5, "2011": 8, "2012": 9, "2013": 10,
    "2014": 11, "2015": 104, "2016": 105, "2017": 106, "2018": 868,
}

PERVENSTVO_YEAR_IDS = {
    "2009": "24813510",
    "2010": "24813512",
    "2011": "24813519",
    "2012": "24813565",
    "2013": "24813568",
    "2014": "24813569",
    "2015": "24813584",
}
PERVENSTVO_SLUG = "pervenstvo-spb-24813508"

KUBOK_FEDERATION_YEAR_IDS = {
    "2016": "24813589",
    "2017": "24813590",
    "2018": "24813594",
}
KUBOK_FEDERATION_SLUG = "kubok-federatsii-spb-24813588"

# Для 2017 года (Кубок Федерации) кнопки фильтра групп по какой-то причине
# не отображаются ни на странице, ни в AJAX-ответе, хотя группы реально
# существуют — ID найдены через анализ реальных запросов браузера (HAR).
MANUAL_GROUP_IDS = {
    "24813590": [("25856129", "А"), ("25856164", "Б")],
}


def fetch_with_retry(url, max_attempts=4, base_delay=4.0, extra_headers=None):
    last_error = None
    headers = dict(HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(base_delay * attempt)
    raise last_error


TEAM_TITLE_RE = re.compile(r'<span class="team-title">\s*([^<]+?)\s*</span>')
TEAM_CITY_RE = re.compile(r'<span class="team-city">.*?</span>', re.DOTALL)
CELL_RE = re.compile(r'<div class="cell[^"]*">\s*([^<]+?)\s*</div>')
TABLE_RE = re.compile(r'<table class="table">.*?<tbody>(.*?)</tbody>', re.DOTALL)
ROW_RE = re.compile(r'<tr>(.*?)</tr>', re.DOTALL)
FILTER_RE = re.compile(r'data-ajax-link="([^"]+)">\s*(Группа\s*[А-Я])\s*</div>')

COLUMN_ORDER = [
    "rank", "games", "wins", "wins_ot", "wins_so",
    "losses_so", "losses_ot", "losses", "goals_for", "goals_against",
    "diff", "points",
]


LOGO_RE = re.compile(r'<img src="(https://img\.fhr\.ru/teams/[^"]+)"')


def parse_standings_table(html):
    table_match = TABLE_RE.search(html)
    if not table_match:
        return []

    tbody_html = table_match.group(1)
    standings = []

    for row_match in ROW_RE.finditer(tbody_html):
        row_html = row_match.group(1)
        team_match = TEAM_TITLE_RE.search(row_html)
        if not team_match:
            continue
        team_name = team_match.group(1).strip()

        logo_match = LOGO_RE.search(row_html)
        logo_url = logo_match.group(1) if logo_match else None

        row_without_team = TEAM_TITLE_RE.sub('', row_html)
        row_without_team = TEAM_CITY_RE.sub('', row_without_team)
        cells = [c.strip() for c in CELL_RE.findall(row_without_team)]

        if len(cells) < len(COLUMN_ORDER):
            continue

        entry = {"team": team_name, "logo_url": logo_url}
        for key, value in zip(COLUMN_ORDER, cells):
            if key == "diff":
                entry[key] = value
            else:
                try:
                    entry[key] = int(value)
                except ValueError:
                    entry[key] = 0

        standings.append(entry)

    standings.sort(key=lambda t: t["rank"])
    return standings


def _build_ajax_url(tournament_id, group_id, year_id):
    import base64
    php_class = base64.b64encode(b"Itprofit\\App\\Ajax\\AjaxComponent").decode()
    php_method = base64.b64encode(b"renderComponent").decode()

    if group_id is None:
        group_serialized = 'N'
    else:
        group_serialized = f's:{len(group_id)}:"{group_id}"'

    params_php = (
        f'a:4:{{s:13:"TOURNAMENT_ID";s:{len(tournament_id)}:"{tournament_id}";'
        f's:8:"GROUP_ID";{group_serialized};'
        f's:7:"YEAR_ID";s:{len(year_id)}:"{year_id}";'
        f's:7:"is_ajax";b:1;}}'
    )
    params_b64 = base64.b64encode(params_php.encode()).decode()

    return (
        f"https://spb.fhr.ru/fhr-ajax/{php_class}/{php_method}/"
        f"?component=itprofit%3Atournament-page&template=.default&params={params_b64}"
    )


def fetch_standings_by_group(tournament_slug, year_id):
    """
    Возвращает {группа: список команд} для турнира+года на spb.fhr.ru.
    Если турнир НЕ разбит на группы — {None: список}.
    Если данных ещё нет (турнир не начался/сайт недоступен) — {}.
    """
    main_url = f"https://spb.fhr.ru/tournaments/{tournament_slug}-year-{year_id}/"
    try:
        html = fetch_with_retry(main_url)
    except Exception as e:
        print(f"[INFO] {main_url} пока недоступен (турнир, вероятно, ещё не начался): {e}")
        return {}

    if year_id in MANUAL_GROUP_IDS:
        tournament_id_match = re.search(r'(\d+)$', tournament_slug)
        tournament_id = tournament_id_match.group(1) if tournament_id_match else ""
        result = {}
        for group_id, group_letter in MANUAL_GROUP_IDS[year_id]:
            full_url = _build_ajax_url(tournament_id, group_id, year_id)
            try:
                group_html = fetch_with_retry(
                    full_url, extra_headers={"X-Requested-With": "XMLHttpRequest", "Referer": main_url}
                )
            except Exception as e:
                print(f"[WARN] Не удалось получить группу {group_letter}: {e}")
                continue
            result[group_letter] = parse_standings_table(group_html)
        return result

    filters = FILTER_RE.findall(html)

    if not filters:
        standings = parse_standings_table(html)
        return {None: standings} if standings else {}

    result = {}
    for link, label in filters:
        group_letter = label.replace("Группа", "").strip()
        full_url = "https://spb.fhr.ru" + link.replace("&amp;", "&")
        try:
            group_html = fetch_with_retry(
                full_url, extra_headers={"X-Requested-With": "XMLHttpRequest", "Referer": main_url}
            )
        except Exception as e:
            print(f"[WARN] Не удалось получить группу {label}: {e}")
            continue
        result[group_letter] = parse_standings_table(group_html)

    return result


def format_standings_title(age, tournament_type):
    return f"🏆 Турнирная таблица — {tournament_type} СПБ {age} г.р."


# ------------------- ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЯ -------------------

FONT_PATH = str(Path(__file__).parent / "fonts" / "PT_Sans-Web-Regular.ttf")
FONT_BOLD_PATH = str(Path(__file__).parent / "fonts" / "PT_Sans-Web-Bold.ttf")

# Рисуем в 2x разрешении — Telegram всё равно сжимает присланное фото под
# экран, и без запаса в исходном изображении текст/логотипы на экранах
# телефонов выглядят пикселизированными. Множитель применяется ко ВСЕМ
# размерам (кроме итоговой ширины, которую удобнее задать напрямую).
SCALE = 6

IMG_WIDTH = 480 * SCALE
ROW_HEIGHT = 22 * SCALE
HEADER_HEIGHT = 40 * SCALE
GROUP_HEADER_HEIGHT = 26 * SCALE
PADDING = 12 * SCALE

COL_RANK_W = 24 * SCALE
COL_STATS_W = 32 * SCALE
COL_TEAM_W = IMG_WIDTH - 2 * PADDING - COL_RANK_W - 4 * COL_STATS_W

COLOR_BG = (255, 255, 255)
COLOR_HEADER_BG = (11, 18, 32)  # #0B1220 — тот же тёмный фон, что у баннеров матчей
COLOR_HEADER_ACCENT = (0, 194, 255)  # #00C2FF — акцентный голубой, как у баннеров
COLOR_HEADER_TEXT = (255, 255, 255)
COLOR_GROUP_BG = (230, 235, 245)
COLOR_GROUP_TEXT = (20, 30, 60)
COLOR_TABLE_HEADER_BG = (245, 246, 248)
COLOR_TEXT = (20, 20, 20)
COLOR_ROW_ALT = (248, 249, 250)
COLOR_BORDER = (220, 220, 220)


NAME_DISPLAY_OVERRIDES = {
    "ВАРЯГИ": "Варяги",
    "ГУДГОЛ": "ГудГол",
    "ДИНАМО": "Динамо СПб",
    "Динамо-юниор": "Динамо-Юниор",
    "ЖХК Динамо-юниор": "ЖХК Динамо-Юниор",
    "Заневский молот": "Заневский Молот",
    "КРАСНАЯ МАШИНА ЮНИОР": "Красная Машина Юниор",
    "КРАСНАЯ МАШИНА ЮНИОР - 2": "Красная Машина Юниор - 2",
    "СЕВЕРСТАЛЬ": "Северсталь",
    "СКА-СЕРЕБРЯНЫЕ ЛЬВЫ": "СКА-Серебряные Львы",
    "СКА-СТРЕЛЬНА": "СКА-Стрельна",
    "СПАРТАК": "Спартак",
    "СШ № 1 МОСКОВСКОГО РАЙОНА": "СШ №1 Московского района",
    'ХК "НЕВСКИЙ" 2016': 'ХК "Невский" 2016',
    'ХК "НЕВСКИЙ" 2017': 'ХК "Невский" 2017',
}


def display_team_name(team_name):
    """Причёсанное написание названия команды — только для отображения в
    сгенерированной таблице, на внутреннее сопоставление матчей не влияет
    (там по-прежнему используется исходное имя, как оно приходит с
    spb.fhr.ru)."""
    if team_name in NAME_DISPLAY_OVERRIDES:
        return NAME_DISPLAY_OVERRIDES[team_name]
    return _prettify_team_name(team_name)


_KEEP_UPPER = {"СКА", "ХКД", "ХК", "ЖХК", "СШ", "СШОР", "ГУАП", "МАХ", "ЦСКА", "ВВС", "УОР"}


def _prettify_team_name(name):
    """Названия не из списка исправлений: слова КАПСОМ -> С заглавной,
    аббревиатуры остаются. 'ХК "НЕВСКИЙ" 2011' -> 'ХК "Невский" 2011'."""
    def fix(word):
        core = word.strip('"«»()')
        if len(core) > 3 and core.isupper() and core.isalpha() and core not in _KEEP_UPPER:
            return word.replace(core, core.capitalize())
        return word
    return " ".join(fix(w) for w in name.split(" "))


LOGO_CACHE = {}
LOGO_SIZE = 24 * SCALE
LOCAL_LOGOS_DIR = Path(__file__).parent / "logos_local"

# Некоторых команд нет в базе spb.fhr.ru (нет логотипа вообще) —
# для них логотип берём из локальной папки logos_local/ вместо сайта.
LOCAL_LOGO_OVERRIDES = {
    "Красные Тигры": "krasnye_tigry.jpeg",
    'ХК "Звезда Юго-Запад"': "zvezda_yugo_zapad.jpeg",
    "Колпино": "kolpino.png",
}


def _get_logo_image(team_name, logo_url):
    """Скачивает и кэширует логотип команды (в памяти процесса — таблица
    формируется одним прогоном, повторно скачивать одно и то же не нужно).
    Если для команды задан локальный файл (LOCAL_LOGO_OVERRIDES) — берём
    его, иначе пробуем скачать с spb.fhr.ru. При любой ошибке (сеть,
    неверный формат) просто возвращает None — тогда строка рисуется без
    логотипа, не ломая всю таблицу."""
    cache_key = LOCAL_LOGO_OVERRIDES.get(team_name) or logo_url
    if cache_key is None:
        return None
    if cache_key in LOGO_CACHE:
        return LOGO_CACHE[cache_key]

    logo = None
    local_filename = LOCAL_LOGO_OVERRIDES.get(team_name)
    try:
        if local_filename:
            logo = Image.open(LOCAL_LOGOS_DIR / local_filename).convert("RGBA")
        elif logo_url:
            resp = requests.get(logo_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            import io
            logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")
        if logo is not None:
            logo = logo.resize((LOGO_SIZE, LOGO_SIZE), Image.LANCZOS)
    except Exception:
        logo = None

    LOGO_CACHE[cache_key] = logo
    return logo


def draw_standings_image(title, by_group, out_path):
    """Рисует турнирную таблицу (одна или несколько групп) как PNG."""
    font_title = ImageFont.truetype(FONT_BOLD_PATH, 17 * SCALE)
    font_group = ImageFont.truetype(FONT_BOLD_PATH, 12 * SCALE)
    font_header = ImageFont.truetype(FONT_BOLD_PATH, 10 * SCALE)
    font_row = ImageFont.truetype(FONT_PATH, 11 * SCALE)

    total_height = HEADER_HEIGHT
    for group_label, standings in by_group.items():
        if not standings:
            continue
        if group_label:
            total_height += GROUP_HEADER_HEIGHT
        total_height += ROW_HEIGHT
        total_height += ROW_HEIGHT * len(standings)
    total_height += PADDING

    img = Image.new('RGB', (IMG_WIDTH, total_height), color=COLOR_BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, IMG_WIDTH, HEADER_HEIGHT], fill=COLOR_HEADER_BG)
    # Диагональная акцентная полоса справа — тот же приём, что и в
    # баннерах матчей (generate_banner.py), для визуального единства.
    draw.polygon(
        [(IMG_WIDTH * 0.80, 0), (IMG_WIDTH, 0), (IMG_WIDTH, HEADER_HEIGHT), (IMG_WIDTH * 0.72, HEADER_HEIGHT)],
        fill=COLOR_HEADER_ACCENT,
    )
    draw.text((PADDING, HEADER_HEIGHT // 2), title, font=font_title, fill=COLOR_HEADER_TEXT, anchor="lm")
    y = HEADER_HEIGHT

    logo_col_w = LOGO_SIZE + 6 * SCALE  # логотип + небольшой отступ до текста названия

    for group_label, standings in by_group.items():
        if not standings:
            continue

        if group_label:
            draw.rectangle([0, y, IMG_WIDTH, y + GROUP_HEADER_HEIGHT], fill=COLOR_GROUP_BG)
            draw.text((PADDING, y + GROUP_HEADER_HEIGHT // 2), f"Группа {group_label}",
                       font=font_group, fill=COLOR_GROUP_TEXT, anchor="lm")
            y += GROUP_HEADER_HEIGHT

        draw.rectangle([0, y, IMG_WIDTH, y + ROW_HEIGHT], fill=COLOR_TABLE_HEADER_BG)
        x = PADDING
        draw.text((x + COL_RANK_W / 2, y + ROW_HEIGHT / 2), "#", font=font_header, fill=COLOR_TEXT, anchor="mm")
        x += COL_RANK_W
        draw.text((x + logo_col_w, y + ROW_HEIGHT / 2), "Команда", font=font_header, fill=COLOR_TEXT, anchor="lm")
        x += COL_TEAM_W
        for label in ["И", "В", "П", "О"]:
            draw.text((x + COL_STATS_W / 2, y + ROW_HEIGHT / 2), label, font=font_header, fill=COLOR_TEXT, anchor="mm")
            x += COL_STATS_W
        y += ROW_HEIGHT
        draw.line([0, y, IMG_WIDTH, y], fill=COLOR_BORDER, width=1)

        for i, t in enumerate(standings):
            if i % 2 == 1:
                draw.rectangle([0, y, IMG_WIDTH, y + ROW_HEIGHT], fill=COLOR_ROW_ALT)

            x = PADDING
            draw.text((x + COL_RANK_W / 2, y + ROW_HEIGHT / 2), str(t["rank"]), font=font_row, fill=COLOR_TEXT, anchor="mm")
            x += COL_RANK_W

            logo = _get_logo_image(t["team"], t.get("logo_url"))
            if logo is not None:
                logo_y = int(y + (ROW_HEIGHT - LOGO_SIZE) / 2)
                img.paste(logo, (int(x), logo_y), logo)
            draw.text((x + logo_col_w, y + ROW_HEIGHT / 2), display_team_name(t["team"]), font=font_row, fill=COLOR_TEXT, anchor="lm")
            x += COL_TEAM_W

            total_losses = t["losses"] + t.get("losses_ot", 0) + t.get("losses_so", 0)
            for value in [t["games"], t["wins"], total_losses, t["points"]]:
                draw.text((x + COL_STATS_W / 2, y + ROW_HEIGHT / 2), str(value), font=font_row, fill=COLOR_TEXT, anchor="mm")
                x += COL_STATS_W
            y += ROW_HEIGHT
            draw.line([0, y, IMG_WIDTH, y], fill=COLOR_BORDER, width=1)

    # Супер-сэмплинг: рисовали в SCALE-кратном разрешении (см. SCALE выше),
    # теперь аккуратно уменьшаем до целевой ширины с качественным
    # сглаживанием (LANCZOS) — это даёт заметно более чёткий текст, чем
    # рисование сразу в целевом размере, и одновременно чуть уменьшает
    # финальный размер файла перед сжатием со стороны Telegram.
    target_width = 1600
    target_height = int(total_height * target_width / IMG_WIDTH)
    img = img.resize((target_width, target_height), Image.LANCZOS)

    IMAGES_DIR.mkdir(exist_ok=True)
    import os
    tmp_path = f"{out_path}.tmp"
    img.save(tmp_path, format="PNG")
    os.replace(tmp_path, out_path)  # подменяем готовый файл целиком
    return out_path


# ------------------- TELEGRAM -------------------

def pin_message(message_id):
    """Закрепляет сообщение в теме — вызывается один раз, при создании
    НОВОГО поста турнирной таблицы (при последующих обновлениях того же
    сообщения закрепление сохраняется само, повторно закреплять не нужно).
    Ошибку не считаем критичной — если закрепить не удалось (например, у
    бота нет прав), сам пост уже отправлен и это не мешает работе."""
    try:
        resp = _tg_post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/pinChatMessage",
            data={"chat_id": TG_CHAT_ID, "message_id": message_id, "disable_notification": True},
            timeout=15,
        )
        result = resp.json()
        if not result.get("ok"):
            print(f"[WARN] Не удалось закрепить сообщение {message_id}: {result}")
    except Exception as e:
        print(f"[WARN] Ошибка при закреплении сообщения {message_id}: {e}")


def _tg_post(url, data=None, files=None, timeout=30):
    """requests.post к Telegram с повтором при SSL-обрыве во время
    соединения (запрос до Telegram не дошёл, повтор безопасен)."""
    last_error = None
    for attempt in range(3):
        if files:
            for f in files.values():
                f.seek(0)
        try:
            return requests.post(url, data=data, files=files, timeout=timeout)
        except requests.exceptions.SSLError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise last_error


def send_photo(topic_id, image_path, caption=""):
    with open(image_path, "rb") as photo_file:
        resp = _tg_post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TG_CHAT_ID,
                "message_thread_id": topic_id,
                "caption": caption,
                "parse_mode": "HTML",
                "disable_notification": True,
            },
            files={"photo": photo_file},
            timeout=30,
        )
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendPhoto error: {result}")
    return result["result"]["message_id"]


def pin_message(message_id):
    """Закрепляет пост в теме — вызывается один раз, сразу после создания
    НОВОГО поста турнирной таблицы (не при каждом обновлении — закреплять
    уже закреплённое сообщение не нужно). Ошибки закрепления не считаем
    критичными (например, если у бота почему-то нет прав) — просто
    сообщаем и продолжаем, самого поста это не касается."""
    resp = _tg_post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/pinChatMessage",
        data={"chat_id": TG_CHAT_ID, "message_id": message_id, "disable_notification": True},
        timeout=30,
    )
    result = resp.json()
    if not result.get("ok"):
        print(f"[WARN] Не удалось закрепить пост {message_id}: {result}")


def edit_photo(message_id, image_path, caption=""):
    media = {"type": "photo", "media": "attach://photo", "caption": caption, "parse_mode": "HTML"}
    with open(image_path, "rb") as photo_file:
        resp = _tg_post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageMedia",
            data={"chat_id": TG_CHAT_ID, "message_id": message_id, "media": json.dumps(media)},
            files={"photo": photo_file},
            timeout=30,
        )
    result = resp.json()
    if not result.get("ok") and "message is not modified" not in str(result.get("description", "")):
        raise RuntimeError(f"Telegram editMessageMedia error: {result}")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ================= Первенство: таблица с fhspb.ru =================
# На fhspb.ru результаты попадают в таблицу сразу после матча, а на
# spb.fhr.ru — с задержкой в дни. Цифры берём с fhspb.ru, логотипы — с
# spb.fhr.ru (там перечислены все команды, даже без сыгранных матчей).
FHSPB_PERVENSTVO = {
    "2009": [(None, 6571)],
    "2010": [(None, 6572)],
    "2011": [("А", 6573), ("Б", 6574)],
    "2012": [("А", 6575), ("Б", 6576)],
    "2013": [("А", 6577), ("Б", 6578)],
    "2014": [("А", 6579), ("Б", 6580)],
    "2015": [("А", 6581), ("Б", 6582)],
}

_FHSPB_TABLE_RE = re.compile(r'<table[^>]*id="StandingsGridView"[^>]*>(.*?)</table>', re.S)
_FHSPB_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.S)
_AGE_TAIL_RE = re.compile(r"\s(?:09|1[0-8])(?=(?:\s\d)?$)")


def _cell_text(raw):
    import html as _html
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", raw)).split())


def _logo_key(name):
    """Ключ для сопоставления логотипов: без регистра, кавычек, ХК/ЖХК,
    дефисов, года/возраста; номер состава сохраняется."""
    t = name.lower().replace("ё", "е")
    t = re.sub(r"[\"«»]", " ", t)
    t = re.sub(r"\b(?:19|20)\d{2}\b", " ", t)
    t = re.sub(r"\b(?:09|1[0-8])\b", " ", t)
    words = [w for w in re.split(r"[\s\-]+", t) if w and w not in ("хк", "жхк")]
    return "".join(words)


def _fhspb_display_name(name):
    """'Динамо Питер 11' -> 'Динамо Питер'; 'Красная Машина Юниор 11 2' ->
    'Красная Машина Юниор - 2'."""
    base = _AGE_TAIL_RE.sub("", name).strip()
    m = re.match(r"^(.*\D)\s(\d)$", base)
    return f"{m.group(1)} - {m.group(2)}" if m else base


def _parse_fhspb_table(table_html):
    rows = []
    for tr in re.split(r"<tr[^>]*>", table_html)[1:]:
        cells = [_cell_text(c) for c in _FHSPB_CELL_RE.findall(tr)]
        if len(cells) < 9 or not cells[0].isdigit():
            continue  # заголовок или мусор
        games, wins, draws, losses, _diff, _pen, points = cells[-7:]
        try:
            rows.append({
                "rank": int(cells[0]), "team": cells[1],
                "games": int(games), "wins": int(wins), "losses": int(losses),
                "losses_ot": 0, "losses_so": 0, "points": int(points),
            })
        except ValueError:
            continue
    rows.sort(key=lambda r: r["rank"])
    return rows


LOGO_MAP_FILE = Path(__file__).parent / "team_logos.json"
_logo_map_cache = None


def _load_logo_map():
    global _logo_map_cache
    if _logo_map_cache is None:
        try:
            _logo_map_cache = json.loads(LOGO_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            _logo_map_cache = {}
    return _logo_map_cache


def _remember_logos(by_group):
    """Запоминает логотипы клубов из таблицы spb.fhr.ru в общий справочник."""
    logos = _load_logo_map()
    changed = False
    for rows in (by_group or {}).values():
        for r in rows:
            url = r.get("logo_url")
            if url:
                key = _logo_key(r["team"])
                if logos.get(key) != url:
                    logos[key] = url
                    changed = True
    if changed:
        LOGO_MAP_FILE.write_text(json.dumps(logos, ensure_ascii=False, indent=2), encoding="utf-8")


def fhspb_pervenstvo_standings(age, spb_by_group):
    """Таблица Первенства с fhspb.ru. При любой проблеме возвращает
    исходные данные spb.fhr.ru (spb_by_group)."""
    config = FHSPB_PERVENSTVO.get(age)
    if not config:
        return spb_by_group
    logos = _load_logo_map()
    result = {}
    try:
        for label, tid in config:
            page = fetch_with_retry(f"https://fhspb.ru/Standings?TournamentID={tid}")
            found = list(_FHSPB_TABLE_RE.finditer(page))
            for i, table_match in enumerate(found, 1):
                rows = _parse_fhspb_table(table_match.group(1))
                for r in rows:
                    r["logo_url"] = logos.get(_logo_key(r["team"]))
                    r["team"] = _fhspb_display_name(r["team"])
                if len(found) == 1:
                    key = label
                else:
                    # Несколько таблиц на странице — группы внутри турнира.
                    # Название группы — ближайший заголовок перед таблицей.
                    before = page[max(0, table_match.start() - 600):table_match.start()]
                    names = re.findall(r"Группа\s*([А-ЯA-Z0-9]+)", before)
                    sub = names[-1] if names else str(i)
                    key = f"{label}{sub}" if label else sub
                result[key] = rows
    except Exception as e:
        print(f"[WARN] fhspb.ru: таблица {age} не получена ({e}) — берём spb.fhr.ru")
        return spb_by_group
    if not any(result.values()):
        return spb_by_group
    return result


def send_album(topic_id, image_paths, caption=""):
    """Альбом из нескольких картинок одним постом; подпись — у первой.
    Возвращает id сообщений альбома по порядку."""
    media = [dict({"type": "photo", "media": f"attach://p{i}"},
                  **({"caption": caption, "parse_mode": "HTML"} if i == 0 else {}))
             for i in range(len(image_paths))]
    files = {f"p{i}": open(p, "rb") for i, p in enumerate(image_paths)}
    try:
        resp = _tg_post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMediaGroup",
                        data={"chat_id": TG_CHAT_ID, "message_thread_id": topic_id,
                              "media": json.dumps(media), "disable_notification": True},
                        files=files, timeout=60)
    finally:
        for f in files.values():
            f.close()
    result = resp.json()
    if not result.get("ok"):
        raise RuntimeError(f"Telegram sendMediaGroup error: {result}")
    return [m["message_id"] for m in result["result"]]


def _table_images(entry, state_key):
    """Картинки уже нарисованной таблицы (одна или по группам) — или []."""
    ids = entry.get("message_ids") or [entry["message_id"]]
    if len(ids) > 1:
        paths = [IMAGES_DIR / f"{state_key}_{i + 1}.png" for i in range(len(ids))]
    else:
        paths = [IMAGES_DIR / f"{state_key}.png"]
    return paths if all(p.exists() for p in paths) else []


def _republish_table(entry, state_key, age, title):
    """Публикует таблицу заново (альбом или фото), закрепляет, убирает старые сообщения."""
    paths = _table_images(entry, state_key)
    if not paths:
        return False
    old_ids = entry.get("message_ids") or [entry["message_id"]]
    ids = send_album(TOPIC_IDS[age], paths, title) if len(paths) > 1 \
        else [send_photo(TOPIC_IDS[age], paths[0], caption=title)]
    pin_message(ids[0])
    entry["message_id"], entry["message_ids"] = ids[0], ids
    for old in old_ids:
        _retire_old_table(old)
    return True


def process_tournament(age, tournament_type, tournament_slug, year_id, state, dry_run):
    topic_id = TOPIC_IDS[age]

    by_group = fetch_standings_by_group(tournament_slug, year_id)
    _remember_logos(by_group)
    if tournament_slug == PERVENSTVO_SLUG:
        by_group = fhspb_pervenstvo_standings(age, by_group)
    # Группы без команд (матчей ещё не было) не показываем; если пусто
    # всё — таблицу не публикуем.
    by_group = {g: s for g, s in by_group.items() if s}
    if not by_group:
        return

    title = format_standings_title(age, tournament_type)
    state_key = f"{tournament_slug}_{year_id}"
    fingerprint = json.dumps({"data": by_group, "overrides": NAME_DISPLAY_OVERRIDES,
                              "local_logos": LOCAL_LOGO_OVERRIDES}, ensure_ascii=False, sort_keys=True)

    groups = list(by_group)
    album = len(groups) > 1           # несколько групп — альбом, картинка на группу
    existing = state.get(state_key)
    old_ids = (existing.get("message_ids") or [existing["message_id"]]) if existing else []
    same_shape = existing is not None and len(old_ids) == (len(groups) if album else 1)

    if same_shape and existing.get("fingerprint") == fingerprint:
        return
    label = ("НОВАЯ ТАБЛИЦА" if existing is None else
             "ОБНОВЛЕНИЕ ТАБЛИЦЫ" if same_shape else "ТАБЛИЦА ПО ГРУППАМ")
    word = "группы" if 2 <= len(groups) <= 4 else "групп"
    print(f"\n[{label}] {age} г.р. {tournament_type}" + (f" ({len(groups)} {word})" if album else ""))
    if dry_run:
        print("  (dry-run — не отправлено)")
        return

    if album:
        paths = []
        for i, g in enumerate(groups):
            path = IMAGES_DIR / f"{state_key}_{i + 1}.png"
            draw_standings_image(title, {g: by_group[g]}, path)
            paths.append(path)
    else:
        paths = [IMAGES_DIR / f"{state_key}.png"]
        draw_standings_image(title, by_group, paths[0])

    if same_shape:
        try:
            for i, (mid, path) in enumerate(zip(old_ids, paths)):
                edit_photo(mid, path, caption=title if i == 0 else "")
            existing["fingerprint"] = fingerprint
            save_state(state)
            time.sleep(1)
            return
        except RuntimeError as e:
            if "message to edit not found" not in str(e):
                raise
            print("[INFO] Сообщение таблицы удалено — публикую заново")

    # Новая таблица, смена вида (одна картинка <-> альбом) или удалённое сообщение
    ids = send_album(topic_id, paths, title) if album else [send_photo(topic_id, paths[0], caption=title)]
    pin_message(ids[0])
    entry = {"message_id": ids[0], "message_ids": ids, "fingerprint": fingerprint}
    if existing and existing.get("reposted_on"):
        entry["reposted_on"] = existing["reposted_on"]
    state[state_key] = entry
    save_state(state)
    for old in old_ids:
        _retire_old_table(old)
    time.sleep(1)


def main():
    import fcntl
    lock_file = open(Path(__file__).parent / "post_standings.lock", "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[INFO] Предыдущий прогон ещё выполняется — пропускаем этот запуск.")
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.live and not args.dry_run:
        print("Укажите --dry-run (тест) или --live (реальная отправка)")
        sys.exit(1)

    dry_run = not args.live
    state = load_state()

    for age, year_id in PERVENSTVO_YEAR_IDS.items():
        try:
            process_tournament(age, "ПЕРВЕНСТВО", PERVENSTVO_SLUG, year_id, state, dry_run)
        except Exception as e:
            print(f"[ERROR] {age}/ПЕРВЕНСТВО: {e}")
        time.sleep(3)

    for age, year_id in KUBOK_FEDERATION_YEAR_IDS.items():
        try:
            process_tournament(age, "КУБОК ФЕДЕРАЦИИ", KUBOK_FEDERATION_SLUG, year_id, state, dry_run)
        except Exception as e:
            print(f"[ERROR] {age}/КУБОК ФЕДЕРАЦИИ: {e}")
        time.sleep(3)

    print("\nГотово.")


# ===================== Перепубликация таблицы в конце игрового дня =====================
from datetime import datetime
REPOST_FALLBACK_HOUR, REPOST_FALLBACK_MINUTE = 23, 30
KUBOK_FEDERATION_FHSPB = {"2016": [6583], "2017": [6584], "2018": [6585]}
_CHESS_MATCH_RE = re.compile(r'MatchID=(\d+)"[^>]*title="[^"]*?(\d{2}\.\d{2}\.\d{4})"')


def _fhspb_tournament_ids(age, tournament_slug):
    if tournament_slug == PERVENSTVO_SLUG:
        return [tid for _, tid in FHSPB_PERVENSTVO.get(age, [])]
    return KUBOK_FEDERATION_FHSPB.get(age, [])


def _day_progress(age, tournament_slug, day):
    """(матчей на день по расписанию, из них с результатом на fhspb.ru)."""
    tids = {str(t) for t in _fhspb_tournament_ids(age, tournament_slug)}
    if not tids:
        return 0, 0
    fixtures_file = Path(__file__).parent / "official_fixtures.json"
    try:
        fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))
    except Exception:
        return 0, 0
    scheduled = {(f["key"], f.get("age")) for f in fixtures
                 if f.get("date") == day and str(f.get("tournament_id")) in tids}
    if not scheduled:
        return 0, 0
    finished = set()
    for tid in tids:
        page = fetch_with_retry(f"https://fhspb.ru/Standings?TournamentID={tid}")
        finished.update(mid for mid, d in _CHESS_MATCH_RE.findall(page) if d == day)
    return len(scheduled), len(finished)


def _retire_old_table(message_id):
    """Удаляет старый пост таблицы; если нельзя (старше 48 ч) — снимает
    закреп и помечает, что актуальная таблица ниже."""
    base = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"
    r = _tg_post(f"{base}/deleteMessage", data={"chat_id": TG_CHAT_ID, "message_id": message_id}).json()
    if r.get("ok") or "not found" in str(r.get("description", "")):
        return
    _tg_post(f"{base}/unpinChatMessage", data={"chat_id": TG_CHAT_ID, "message_id": message_id})
    _tg_post(f"{base}/editMessageCaption", data={"chat_id": TG_CHAT_ID, "message_id": message_id,
                                                 "caption": "⬇️ Таблица обновлена — актуальная ниже"})
    print(f"[INFO] Старую таблицу {message_id} удалить нельзя (старше 48 ч) — снят закреп, подпись заменена")


def _maybe_daily_repost(age, tournament_type, tournament_slug, year_id, state, dry_run, was_new):
    state_key = f"{tournament_slug}_{year_id}"
    entry = state.get(state_key)
    now = datetime.now()
    today = now.strftime("%d.%m.%Y")
    if not entry or entry.get("reposted_on") == today:
        return
    if was_new:
        entry["reposted_on"] = today     # таблицу и так только что опубликовали
        save_state(state)
        return
    if not _table_images(entry, state_key):
        return
    scheduled, finished = _day_progress(age, tournament_slug, today)
    if not scheduled or not finished:
        return
    late = (now.hour, now.minute) >= (REPOST_FALLBACK_HOUR, REPOST_FALLBACK_MINUTE)
    if finished < scheduled and not late:
        return
    print(f"\n[ПЕРЕПУБЛИКАЦИЯ ТАБЛИЦЫ] {age} г.р. {tournament_type}: сыграно {finished} из {scheduled}")
    if dry_run:
        print("  (dry-run — не отправлено)")
        return
    if _republish_table(entry, state_key, age, format_standings_title(age, tournament_type)):
        entry["reposted_on"] = today
        save_state(state)


_process_tournament_single_post = process_tournament


def process_tournament(age, tournament_type, tournament_slug, year_id, state, dry_run):
    """Обычное обновление таблицы + перепубликация в конце игрового дня."""
    was_new = f"{tournament_slug}_{year_id}" not in state
    _process_tournament_single_post(age, tournament_type, tournament_slug, year_id, state, dry_run)
    try:
        _maybe_daily_repost(age, tournament_type, tournament_slug, year_id, state, dry_run, was_new)
    except Exception as e:
        print(f"[WARN] Перепубликация {age} {tournament_type}: {e}")


if __name__ == "__main__":
    main()
