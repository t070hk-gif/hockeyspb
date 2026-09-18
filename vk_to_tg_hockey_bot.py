#!/usr/bin/env python3
"""
Бот: пересылка расписания хоккейных игр (видео из постов ВК) в Telegram-канал.

Ключи матчей включают возраст (если известен) и сохраняют номер состава —
предотвращает коллизии между разными возрастами и составами клубов.
"""

import json
import re
import time
from pathlib import Path

import requests

VK_API_VERSION = "5.199"
VK_CLIENT_ID = "54726270"
VK_TOKEN_REFRESH_URL = "https://id.vk.ru/oauth2/auth"

TOKEN_FILE = Path(__file__).parent / "vk_tokens.json"
TEAMS_FILE = Path(__file__).parent / "teams.json"
VIDEO_INDEX_FILE = Path(__file__).parent / "video_index.json"
FRIENDLY_BANNERS_DIR = Path(__file__).parent / "banners_friendly"
OFFICIAL_MATCHES_FILE = Path(__file__).parent / "official_matches.json"

VK_GROUP_IDS = [
    214108632,
    211881014,
    227274350,
    99334801,
    110125126,
    210582936,
    219803675,
    25510790,
    165020927,
    133823152,
    136729253,
    227371906,
    120045135,
    27313226,
    114375744,
    226770005,
]

ROSSII_ONLY_GROUP_IDS = {25510790, 165020927, 133823152}

TG_BOT_TOKEN = "7972710769:AAGA1FQ1_Sh7K2EtTvCvzji-SJPxZ-kp_54"
TG_CHANNEL_ID = -1002723611949

POLL_INTERVAL_SECONDS = 300
POSTS_PER_CHECK = 20

STATE_FILE = Path(__file__).parent / "state.json"


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_tokens():
    if not TOKEN_FILE.exists():
        raise SystemExit(f"Файл {TOKEN_FILE} не найден. Сначала получите токен через get_vk_token.py")
    return json.loads(TOKEN_FILE.read_text(encoding="utf-8"))


def save_tokens(data):
    data["obtained_at"] = int(time.time())
    TOKEN_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_access_token(tokens):
    refresh_token = tokens.get("refresh_token")
    device_id = tokens.get("device_id")

    if not refresh_token:
        raise SystemExit("В vk_tokens.json нет refresh_token — заново пройдите авторизацию через get_vk_token.py")
    if not device_id:
        raise SystemExit("В vk_tokens.json нет device_id — заново пройдите авторизацию через get_vk_token.py.")

    resp = requests.post(
        VK_TOKEN_REFRESH_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": VK_CLIENT_ID,
            "refresh_token": refresh_token,
            "device_id": device_id,
        },
        timeout=15,
    )

    new_data = resp.json()

    if resp.status_code != 200 or "access_token" not in new_data:
        raise SystemExit(
            f"Не удалось обновить токен (HTTP {resp.status_code}).\n"
            f"Полный ответ сервера: {new_data}\n\n"
            "Возможно, refresh_token истёк или отозван — заново пройдите авторизацию через get_vk_token.py"
        )

    new_data.setdefault("device_id", device_id)
    print("[VK] Токен успешно обновлён через refresh_token.")
    save_tokens(new_data)
    return new_data


def get_valid_access_token(tokens):
    obtained_at = tokens.get("obtained_at", 0)
    expires_in = tokens.get("expires_in", 3600)
    expires_at = obtained_at + expires_in

    if time.time() >= expires_at - 120:
        tokens = refresh_access_token(tokens)

    return tokens["access_token"], tokens


def vk_get_wall_posts(access_token, group_id, count=POSTS_PER_CHECK):
    resp = requests.get(
        "https://api.vk.com/method/wall.get",
        params={
            "owner_id": -abs(group_id),
            "count": count,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    data = resp.json()
    if "error" in data:
        print(f"[VK API error] group {group_id}: {data['error']}")
        return []
    return data.get("response", {}).get("items", [])


VIDEO_CATALOG_PER_CHECK = 40


def vk_get_group_videos(access_token, group_id, count=VIDEO_CATALOG_PER_CHECK):
    resp = requests.get(
        "https://api.vk.com/method/video.get",
        params={
            "owner_id": -abs(group_id),
            "count": count,
            "access_token": access_token,
            "v": VK_API_VERSION,
        },
        timeout=15,
    )
    data = resp.json()
    if "error" in data:
        print(f"[VK API error - video.get] group {group_id}: {data['error']}")
        return None
    return data.get("response", {}).get("items", [])


def extract_videos_from_post(post):
    videos = []
    post_date = post.get("date")
    known_owner_ids = {-abs(g) for g in VK_GROUP_IDS}

    for att in post.get("attachments", []) or []:
        if att.get("type") == "video" and "video" in att:
            video = att["video"]
            if "date" not in video and post_date:
                video = {**video, "date": post_date}
            videos.append(video)

    for repost in post.get("copy_history", []) or []:
        repost_date = repost.get("date", post_date)
        for att in repost.get("attachments", []) or []:
            if att.get("type") == "video" and "video" in att:
                video = att["video"]
                if video.get("owner_id") not in known_owner_ids:
                    continue
                if "date" not in video and repost_date:
                    video = {**video, "date": repost_date}
                videos.append(video)

    return videos


def load_known_teams():
    if not TEAMS_FILE.exists():
        return []

    data = json.loads(TEAMS_FILE.read_text(encoding="utf-8"))
    base_names = set()
    suffix_re = re.compile(r'\s\d{1,2}(\s\d+)?$')

    for age_group, teams in data.items():
        for name in teams:
            base = suffix_re.sub('', name).strip()
            if base.endswith('№'):
                base = name.strip()
            if base:
                base_names.add(base)
                base_names.add(f"ЖХК {base}")

    return sorted(base_names, key=len, reverse=True)


def find_known_teams_with_positions(title, known_teams):
    found = []
    remaining = title
    for team in known_teams:
        is_zhk = team.upper().startswith("ЖХК ")
        if is_zhk:
            rest = team[4:]
            rest_pattern = re.escape(rest).replace(r"\ ", r"[\s\-]")
            pattern_str = r"ЖХК\s*[\"'«]?\s*" + rest_pattern + r"\b"
        else:
            pattern_str = r"\b" + re.escape(team).replace(r"\ ", r"[\s\-]") + r"\b"
        pattern = re.compile(pattern_str, re.IGNORECASE)

        while True:
            m = pattern.search(remaining)
            if not m:
                break
            if not is_zhk:
                preceding = remaining[max(0, m.start() - 12):m.start()].upper()
                if "ЖХК" in preceding:
                    remaining = remaining[:m.start()] + " " * (m.end() - m.start()) + remaining[m.end():]
                    continue
            matched_team = team
            squad_match = re.match(r'\s*"?\s*(\d)\b(?!\d)', title[m.end():m.end() + 6])
            if squad_match:
                matched_team = f"{team} {squad_match.group(1)}"

            found.append((m.start(), m.end(), matched_team))
            remaining = remaining[:m.start()] + " " * (m.end() - m.start()) + remaining[m.end():]
    found.sort(key=lambda x: x[0])

    filtered = []
    for i, (start, end, team) in enumerate(found):
        if i + 1 < len(found):
            next_start, next_end, next_team = found[i + 1]
            gap = title[end:next_start]
            if gap.strip() == "" and team.upper() in next_team.upper():
                continue
        filtered.append((start, end, team))

    return filtered


def find_known_teams_in_title(title, known_teams):
    return [name for _, _, name in find_known_teams_with_positions(title, known_teams)]


KNOWN_TEAMS = load_known_teams()

KUBOK_ROSSII_TEAMS_FILE = Path(__file__).parent / "kubok_rossii_teams.json"


def load_known_teams_rossii():
    if not KUBOK_ROSSII_TEAMS_FILE.exists():
        return []
    teams = json.loads(KUBOK_ROSSII_TEAMS_FILE.read_text(encoding="utf-8"))
    return sorted(set(teams), key=len, reverse=True)


KNOWN_TEAMS_ROSSII = load_known_teams_rossii()

from datetime import datetime

RU_MONTHS = {
    'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4, 'мая': 5, 'июня': 6,
    'июля': 7, 'августа': 8, 'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12,
}

DATE_NUMERIC_RE = re.compile(r'\b(\d{1,2})\.(\d{1,2})\.(\d{2,4})\b')
DATE_NUMERIC_NOYEAR_RE = re.compile(r'\b(\d{1,2})\.(\d{1,2})\b(?!\.\d)')
DATE_RU_WORDS_RE = re.compile(
    r'\b(\d{1,2})\s+(' + '|'.join(RU_MONTHS.keys()) + r')\s+(\d{4})\b',
    re.IGNORECASE,
)
TIME_RE = re.compile(r'\b([01]?\d|2[0-3]):([0-5]\d)\b')
AGE_TOKEN_RE = re.compile(r'(?<![.\d:])(09|1[0-8])(?![.\d:])')
FULL_YEAR_AGE_RE = re.compile(r'\b20(09|1[0-8])\b')

DEFAULT_YEAR = 2026

NOISE_WORDS = [
    "МСК", "г.р.", "Товарищеская игра", "Live:",
]
EXCLUDE_KEYWORDS = [
    "ВОДНОЕ ПОЛО", "БАСКЕТБОЛ", "ФУТБОЛ", "ВОЛЕЙБОЛ",
    "ОБЗОР МАТЧА", "ОБЗОР ИГРЫ", "ОБЗОР",
    "ТРЕНИРОВКА",
]

TEAM_DASH_RE = re.compile(r'\s[-–—]\s')
BIRTH_YEAR_RE = re.compile(r'\b(19|20)\d{2}(-(19|20)?\d{2})?\b')


def _extract_date(title):
    m = DATE_RU_WORDS_RE.search(title)
    if m:
        day, month_name, year = m.groups()
        month = RU_MONTHS[month_name.lower()]
        return f"{int(day):02d}.{month:02d}.{year}", m.group(0)

    m = DATE_NUMERIC_RE.search(title)
    if m:
        day, month, year = m.groups()
        if len(year) == 2:
            year = f"20{year}"
        return f"{day}.{month}.{year}", m.group(0)

    m = DATE_NUMERIC_NOYEAR_RE.search(title)
    if m:
        day, month = m.groups()
        return f"{day}.{month}.{DEFAULT_YEAR}", m.group(0)

    return None, None


def _extract_teams(title, date_match, time_match):
    core = title
    if date_match:
        core = core.replace(date_match, " ")
    if time_match:
        core = core.replace(time_match, " ")
    for noise in NOISE_WORDS:
        core = re.sub(re.escape(noise), " ", core, flags=re.IGNORECASE)

    if "•" in core:
        segments = [s.strip() for s in core.split("•")]
        dash_segments = [s for s in segments if TEAM_DASH_RE.search(s)]
        if dash_segments:
            core = dash_segments[0]

    core = re.sub(r'\([^)]*\)', ' ', core)
    core = re.sub(r'[|/]', ' ', core)
    core = BIRTH_YEAR_RE.sub(' ', core)
    core = re.sub(r'\s+', ' ', core).strip(" .,-–—")

    if ". " in core:
        prefix, _, rest = core.partition(". ")
        if TEAM_DASH_RE.search(rest) and not TEAM_DASH_RE.search(prefix):
            core = rest.strip()

    core = core.replace('"', '').replace('«', '').replace('»', '')
    core = re.sub(r'\s+', ' ', core).strip(" .,-–—")

    return core if core else None


def parse_video_title(title, description="", upload_timestamp=None, live_start_time=None,
                       extra_known_teams=None):
    result = {"date": None, "time": None, "teams": None, "age": None, "alt_teams": None,
               "teams_verified": False}

    combined_for_exclusion = f"{title} {description}".upper()
    if any(kw in combined_for_exclusion for kw in EXCLUDE_KEYWORDS):
        return result

    date_str, date_match = _extract_date(title)

    time_match_obj = TIME_RE.search(description) or TIME_RE.search(title)
    time_match_str = time_match_obj.group(0) if time_match_obj else None
    if time_match_obj:
        result["time"] = f"{time_match_obj.group(1)}:{time_match_obj.group(2)}"

    teams = None
    alt_teams = None
    teams_verified = False

    effective_known_teams = KNOWN_TEAMS
    if extra_known_teams:
        effective_known_teams = sorted(set(KNOWN_TEAMS) | set(extra_known_teams), key=len, reverse=True)

    if effective_known_teams:
        matched_pos = find_known_teams_with_positions(title, effective_known_teams)
        if len(matched_pos) >= 2:
            teams = f"{matched_pos[0][2]} — {matched_pos[1][2]}"
            teams_verified = True

            if len(matched_pos) >= 3:
                gap = title[matched_pos[1][1]:matched_pos[2][0]]
                if "/" in gap:
                    alt_teams = f"{matched_pos[0][2]} — {matched_pos[2][2]}"

    if not teams:
        heuristic_teams = _extract_teams(title, date_match, time_match_str)
        if heuristic_teams and TEAM_DASH_RE.search(heuristic_teams):
            teams = heuristic_teams

    age_match = AGE_TOKEN_RE.search(title)
    if age_match:
        result["age"] = age_match.group(1)
    else:
        full_year_match = FULL_YEAR_AGE_RE.search(title)
        if full_year_match:
            result["age"] = full_year_match.group(1)

    if teams:
        result["teams"] = teams
        result["alt_teams"] = alt_teams

        if not date_str and description:
            desc_date_str, _ = _extract_date(description)
            if desc_date_str:
                date_str = desc_date_str

        if not date_str and live_start_time:
            dt = datetime.fromtimestamp(live_start_time)
            date_str = dt.strftime("%d.%m.%Y")

        if not result["time"] and live_start_time:
            dt = datetime.fromtimestamp(live_start_time)
            result["time"] = dt.strftime("%H:%M")

        if not date_str and upload_timestamp:
            dt = datetime.fromtimestamp(upload_timestamp)
            date_str = dt.strftime("%d.%m.%Y")

    result["date"] = date_str
    result["teams_verified"] = teams_verified
    return result


def get_friendly_banner_path(age):
    if age:
        full_year = f"20{age}"
        path = FRIENDLY_BANNERS_DIR / f"friendly_{full_year}.png"
        if path.exists():
            return path
    return FRIENDLY_BANNERS_DIR / "friendly_unknown.png"


def send_photo_to_telegram(banner_path, caption):
    with open(banner_path, "rb") as photo_file:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TG_CHANNEL_ID,
                "caption": caption,
                "parse_mode": "HTML",
                "disable_notification": True,
            },
            files={"photo": photo_file},
            timeout=30,
        )
    data = resp.json()
    ok = resp.status_code == 200 and data.get("ok")
    if not ok:
        print(f"[Telegram error] {resp.status_code}: {resp.text}")
        return None
    return data["result"]["message_id"]


def edit_photo_message(message_id, banner_path, caption):
    media = {
        "type": "photo",
        "media": "attach://photo",
        "caption": caption,
        "parse_mode": "HTML",
    }
    with open(banner_path, "rb") as photo_file:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageMedia",
            data={"chat_id": TG_CHANNEL_ID, "message_id": message_id, "media": json.dumps(media)},
            files={"photo": photo_file},
            timeout=30,
        )
    data = resp.json()
    ok = resp.status_code == 200 and data.get("ok")
    description = str(data.get("description", ""))
    if not ok and "message is not modified" not in description:
        print(f"[Telegram error - edit] {resp.status_code}: {resp.text}")
        if "message to edit not found" in description or "MESSAGE_ID_INVALID" in description:
            return "not_found"
    return ok


def get_friendly_group_key(age, date_str):
    return f"{age or 'unknown'}_{date_str}"


def format_friendly_day_caption(date_str, matches):
    lines = [f"📅 {date_str} — Товарищеские игры", ""]

    sorted_matches = sorted(matches.values(), key=lambda m: m.get("time") or "99:99")

    for m in sorted_matches:
        teams_line = f"👥 {m['teams']}"
        if m.get("age"):
            teams_line += f" (20{m['age']} г.р.)"
        lines.append(teams_line)
        if m.get("time"):
            lines.append(f"🕐 {m['time']}")
        lines.append(f'🔗 <a href="{m["video_url"]}">Смотреть трансляцию ВКонтакте</a>')
        lines.append("")

    return "\n".join(lines).strip()


AGE_SUFFIX_RE = re.compile(r'\s+\d{1,2}(-\d{1,2})?(\s+(\d+))?$')
FULL_YEAR_SUFFIX_RE = re.compile(r'\s+(19|20)\d{2}(\s+(\d+))?$')


def _strip_suffix_keep_squad_number(name, pattern):
    m = pattern.search(name)
    if not m:
        return name
    squad_num = m.groups()[-1] if m.groups() else None
    base = name[:m.start()].rstrip()
    return f"{base} {squad_num}" if squad_num else base


def normalize_team_name(name):
    if not name:
        return ""
    name = name.strip()
    original = name
    stripped = _strip_suffix_keep_squad_number(name, FULL_YEAR_SUFFIX_RE)
    name = stripped if stripped != name else _strip_suffix_keep_squad_number(name, AGE_SUFFIX_RE)
    if name.endswith('№'):
        name = original
    name = re.sub(r'^ХК\s*', '', name, flags=re.IGNORECASE)
    name = name.replace('«', '').replace('»', '').replace('"', '')
    name = name.replace('-', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name.lower()


def normalize_team_name_rossii(name):
    name = normalize_team_name(name)
    if name == "динамо":
        name = "динамо спб"
    return name.strip()


def build_match_key(date_str, team1, team2, age=None):
    t1, t2 = normalize_team_name(team1), normalize_team_name(team2)
    teams_part = "|".join(sorted([t1, t2]))
    age_part = f"::{age}" if age else ""
    return f"{date_str}::{teams_part}{age_part}"


def build_match_key_rossii(date_str, team1, team2, age=None):
    t1, t2 = normalize_team_name_rossii(team1), normalize_team_name_rossii(team2)
    teams_part = "|".join(sorted([t1, t2]))
    age_part = f"::{age}" if age else ""
    return f"{date_str}::{teams_part}{age_part}"


def load_video_index():
    if VIDEO_INDEX_FILE.exists():
        return json.loads(VIDEO_INDEX_FILE.read_text(encoding="utf-8"))
    return {}


def save_video_index(index):
    VIDEO_INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def load_official_matches():
    if OFFICIAL_MATCHES_FILE.exists():
        return set(json.loads(OFFICIAL_MATCHES_FILE.read_text(encoding="utf-8")))
    return set()


def is_official_match(parsed, official_keys):
    if not parsed["teams"] or not parsed["date"] or not official_keys:
        return False

    for teams_str in filter(None, [parsed["teams"], parsed.get("alt_teams")]):
        team_parts = TEAM_DASH_RE.split(teams_str)
        if len(team_parts) != 2:
            continue
        team1, team2 = team_parts[0].strip(), team_parts[1].strip()
        key = build_match_key(parsed["date"], team1, team2)
        if key in official_keys:
            return True

    return False


def register_video_in_index(parsed, video):
    if not parsed["teams"] or not parsed["date"]:
        return

    video_url = f"https://vk.com/video{video['owner_id']}_{video['id']}"
    index = load_video_index()

    for teams_str in filter(None, [parsed["teams"], parsed.get("alt_teams")]):
        team_parts = TEAM_DASH_RE.split(teams_str)
        if len(team_parts) != 2:
            continue
        team1, team2 = team_parts[0].strip(), team_parts[1].strip()

        entry = {"video_url": video_url, "title": video.get("title", "")}
        age = parsed.get("age")

        key = build_match_key(parsed["date"], team1, team2)
        index[key] = entry

        rossii_key = build_match_key_rossii(parsed["date"], team1, team2)
        if rossii_key != key:
            index[rossii_key] = entry

        if age:
            key_age = build_match_key(parsed["date"], team1, team2, age=age)
            index[key_age] = entry

            rossii_key_age = build_match_key_rossii(parsed["date"], team1, team2, age=age)
            if rossii_key_age != key_age:
                index[rossii_key_age] = entry

    save_video_index(index)


def check_groups_once(state, access_token):
    catalog_baseline = state.setdefault("_catalog_baseline_done", {})
    official_keys = load_official_matches()

    for group_id in VK_GROUP_IDS:
        key = str(group_id)
        seen_video_ids = set(state.get(key, []))

        posts = vk_get_wall_posts(access_token, group_id)
        wall_videos = []
        for post in posts:
            wall_videos.extend(extract_videos_from_post(post))

        catalog_videos = vk_get_group_videos(access_token, group_id)
        catalog_fetch_failed = catalog_videos is None
        if catalog_fetch_failed:
            catalog_videos = []

        if not catalog_baseline.get(key):
            if catalog_fetch_failed:
                pass
            else:
                for v in catalog_videos:
                    seen_video_ids.add(v["id"])
                catalog_baseline[key] = True
                state[key] = sorted(seen_video_ids)
                save_state(state)
                print(f"[INFO] Базовая линия видео-каталога установлена для группы {group_id} "
                      f"({len(catalog_videos)} видео помечено как уже виденные)")

        all_videos = wall_videos + catalog_videos
        if not all_videos:
            continue

        unique_videos = {}
        for v in all_videos:
            unique_videos[v["id"]] = v

        sent_videos = state.setdefault("_sent_videos", {})
        day_posts = state.setdefault("_friendly_day_posts", {})

        for vid, video in unique_videos.items():
            vid_str = str(vid)
            snapshot = sent_videos.get(vid_str)
            if not snapshot:
                continue

            if group_id in ROSSII_ONLY_GROUP_IDS:
                continue

            current_title = video.get("title", "")
            current_description = video.get("description", "")
            if (current_title == snapshot["title"]
                    and current_description == snapshot["description"]):
                continue

            print(f"[EDIT-CHECK] Видео {vid} изменилось: {snapshot['title']!r} -> {current_title!r}")

            upload_ts = video.get("date")
            live_start = video.get("live_start_time")
            new_parsed = parse_video_title(current_title, current_description,
                                            upload_timestamp=upload_ts, live_start_time=live_start)

            if not new_parsed["teams"] and not new_parsed["date"]:
                continue

            if is_official_match(new_parsed, official_keys):
                print(f"[WARN] Видео {vid} после правки стало официальным матчем — "
                      f"рекомендуется вручную проверить пост дня {snapshot.get('group_key')}")
                sent_videos[vid_str] = {"group_key": snapshot.get("group_key"),
                                         "title": current_title, "description": current_description}
                save_state(state)
                continue

            if new_parsed["teams"] and not new_parsed.get("teams_verified"):
                print(f"[SKIP] Видео {vid} - после правки команды не подтверждены официальным списком, пост не трогаем: {current_title}")
                sent_videos[vid_str] = {"group_key": snapshot.get("group_key"),
                                         "title": current_title, "description": current_description}
                save_state(state)
                continue

            register_video_in_index(new_parsed, video)

            video_url = f"https://vk.com/video{video['owner_id']}_{video['id']}"
            new_match_entry = {"teams": new_parsed["teams"], "age": new_parsed.get("age"),
                                "time": new_parsed.get("time"), "video_url": video_url}
            new_group_key = get_friendly_group_key(new_parsed.get("age"), new_parsed["date"])
            old_group_key = snapshot.get("group_key")

            if old_group_key and old_group_key != new_group_key:
                old_post = day_posts.get(old_group_key)
                if old_post and vid_str in old_post["matches"]:
                    del old_post["matches"][vid_str]
                    if old_post["matches"]:
                        old_age, old_date = old_group_key.split("_", 1)
                        old_caption = format_friendly_day_caption(old_date, old_post["matches"])
                        old_banner = get_friendly_banner_path(None if old_age == "unknown" else old_age)
                        if edit_photo_message(old_post["message_id"], old_banner, old_caption) == "not_found":
                            day_posts.pop(old_group_key, None)

            target_post = day_posts.get(new_group_key)
            new_banner_path = get_friendly_banner_path(new_parsed.get("age"))

            if target_post is None:
                matches = {vid_str: new_match_entry}
                caption = format_friendly_day_caption(new_parsed["date"], matches)
                msg_id = send_photo_to_telegram(new_banner_path, caption)
                if msg_id:
                    day_posts[new_group_key] = {"message_id": msg_id, "matches": matches}
                    print(f"[OK] Пост дня создан после правки ({new_group_key}), видео {vid}")
            else:
                target_post["matches"][vid_str] = new_match_entry
                caption = format_friendly_day_caption(new_parsed["date"], target_post["matches"])
                result = edit_photo_message(target_post["message_id"], new_banner_path, caption)
                if result == "not_found":
                    print(f"[WARN] Пост дня ({new_group_key}) больше не существует — очищаем ссылку")
                    day_posts.pop(new_group_key, None)
                elif result:
                    print(f"[OK] Пост дня обновлён после правки ({new_group_key}), видео {vid}")

            sent_videos[vid_str] = {"group_key": new_group_key,
                                     "title": current_title, "description": current_description}
            save_state(state)

        new_videos = [v for vid, v in unique_videos.items() if vid not in seen_video_ids]
        new_videos.sort(key=lambda v: v.get("date", 0))

        first_run = key not in state

        for video in new_videos:
            if first_run:
                seen_video_ids.add(video["id"])
                continue

            title = video.get("title", "")
            description = video.get("description", "")
            upload_ts = video.get("date")
            live_start = video.get("live_start_time")
            extra_teams = KNOWN_TEAMS_ROSSII if group_id in ROSSII_ONLY_GROUP_IDS else None
            parsed = parse_video_title(title, description, upload_timestamp=upload_ts,
                                        live_start_time=live_start, extra_known_teams=extra_teams)

            if not parsed["teams"] and not parsed["date"]:
                seen_video_ids.add(video["id"])
                continue

            register_video_in_index(parsed, video)

            if parsed["teams"] and not parsed.get("teams_verified"):
                print(f"[SKIP] Видео {video['id']} — команды не подтверждены официальным "
                      f"списком, не публикуем в общий чат: {title}")
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue

            if group_id in ROSSII_ONLY_GROUP_IDS:
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue

            if is_official_match(parsed, official_keys):
                print(f"[SKIP] Видео {video['id']} — официальный матч турнира, "
                      f"не дублируем в общий чат: {title}")
                seen_video_ids.add(video["id"])
                state[key] = sorted(seen_video_ids)
                save_state(state)
                continue

            vid_str = str(video["id"])
            video_url = f"https://vk.com/video{video['owner_id']}_{video['id']}"
            match_entry = {"teams": parsed["teams"], "age": parsed.get("age"),
                            "time": parsed.get("time"), "video_url": video_url}
            group_key = get_friendly_group_key(parsed.get("age"), parsed["date"])
            banner_path = get_friendly_banner_path(parsed.get("age"))

            post = day_posts.get(group_key)

            if post is None:
                matches = {vid_str: match_entry}
                caption = format_friendly_day_caption(parsed["date"], matches)
                sent_message_id = send_photo_to_telegram(banner_path, caption)
                if sent_message_id:
                    print(f"[OK] Новый пост дня создан ({group_key}), видео {video['id']}: {title}")
                    day_posts[group_key] = {"message_id": sent_message_id, "matches": matches}
                else:
                    print(f"[FAIL] Не удалось создать пост дня ({group_key}) для видео {video['id']}")
                    continue
            else:
                post["matches"][vid_str] = match_entry
                caption = format_friendly_day_caption(parsed["date"], post["matches"])
                result = edit_photo_message(post["message_id"], banner_path, caption)
                if result == "not_found":
                    print(f"[WARN] Пост дня ({group_key}) больше не существует — создаём заново")
                    new_msg_id = send_photo_to_telegram(banner_path, caption)
                    if new_msg_id:
                        day_posts[group_key] = {"message_id": new_msg_id, "matches": post["matches"]}
                        print(f"[OK] Пост дня пересоздан ({group_key}), видео {video['id']}: {title}")
                    else:
                        print(f"[FAIL] Не удалось пересоздать пост дня ({group_key}) для видео {video['id']}")
                        continue
                elif result:
                    print(f"[OK] Пост дня дополнен ({group_key}), видео {video['id']}: {title}")
                else:
                    print(f"[FAIL] Не удалось обновить пост дня ({group_key}) для видео {video['id']}")
                    continue

            seen_video_ids.add(video["id"])
            state[key] = sorted(seen_video_ids)
            sent_videos[vid_str] = {"group_key": group_key, "title": title, "description": description}
            save_state(state)

        state[key] = sorted(seen_video_ids)
        save_state(state)


def main():
    state = load_state()
    tokens = load_tokens()
    print("Бот запущен. Проверка групп каждые", POLL_INTERVAL_SECONDS, "секунд.")

    while True:
        try:
            access_token, tokens = get_valid_access_token(tokens)
            check_groups_once(state, access_token)
        except SystemExit as e:
            print(f"[FATAL] {e}")
            break
        except Exception as e:
            print(f"[ERROR] {e}")
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
