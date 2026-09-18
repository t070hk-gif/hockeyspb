#!/usr/bin/env python3
"""
Итоговый бот: тянет расписание/результаты с fhspb.ru, группирует матчи по
дням, подбирает нужный баннер и публикует один пост на день. Ключи матчей
включают возраст (если известен) и сохраняют номер состава — предотвращает
коллизии между разными возрастами и составами одних и тех же клубов.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

try:
    import spb_fhr_client
except ImportError:
    spb_fhr_client = None

TG_BOT_TOKEN = "7972710769:AAGA1FQ1_Sh7K2EtTvCvzji-SJPxZ-kp_54"
TG_CHAT_ID = -1002723611949

BANNERS_DIR = Path(__file__).parent / "banners"
STATE_FILE = Path(__file__).parent / "posted_days.json"
VIDEO_INDEX_FILE = Path(__file__).parent / "video_index.json"
OFFICIAL_MATCHES_FILE = Path(__file__).parent / "official_matches.json"
SPB_DETAILS_CACHE_FILE = Path(__file__).parent / "spb_match_details.json"
KUBOK_ROSSII_TEAMS_FILE = Path(__file__).parent / "kubok_rossii_teams.json"
LOCK_FILE = Path(__file__).parent / "post_schedule.lock"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TOPIC_IDS = {
    "2009": 3, "2010": 5, "2011": 8, "2012": 9, "2013": 10,
    "2014": 11, "2015": 104, "2016": 105, "2017": 106, "2018": 868,
}

CUP_CONFIG = {
    "2010": 6565, "2011": 6566, "2012": 6567, "2013": 6568,
    "2014": 6569, "2015": 6570, "2016": 6583, "2017": 6584, "2018": 6585,
}

CHAMPIONSHIP_CONFIG = [
    ("2009", None, 6571), ("2010", None, 6572),
    ("2011", "A", 6573), ("2011", "Б", 6574),
    ("2012", "A", 6575), ("2012", "Б", 6576),
    ("2013", "A", 6577), ("2013", "Б", 6578),
    ("2014", "A", 6579), ("2014", "Б", 6580),
    ("2015", "A", 6581), ("2015", "Б", 6582),
]

MATCH_ROW_RE = re.compile(
    r'<td style="white-space:nowrap;">([^<]+)</td>'
    r'<td class="text-center">\s*<span class="label secondary(?: round)?">([\d:]+)</span>\s*</td>'
    r'<td class="text-center">\s*<a href="/?Arena\?[^"]*"[^>]*>([^<]*)</a>\s*</td>'
    r'<td>\s*<a href="/?Match\?TournamentID=(\d+)&MatchID=(\d+)">([^<]+)</a>\s*</td>'
    r'<td class="text-center" style="font-size:Larger;font-weight:bold;white-space:nowrap;">([^<]*)</td>',
    re.DOTALL
)

MATCH_ROW_NO_SCORE_RE = re.compile(
    r'<td style="white-space:nowrap;">([^<]+)</td>'
    r'<td class="text-center">\s*<span class="label secondary(?: round)?">([\d:]+)</span>\s*</td>'
    r'<td class="text-center">\s*<a href="/?Arena\?[^"]*"[^>]*>([^<]*)</a>\s*</td>'
    r'<td>\s*<a href="/?Match\?TournamentID=(\d+)&MatchID=(\d+)">([^<]+)</a>\s*</td>',
    re.DOTALL
)


def fetch_with_retry(url, max_attempts=6, base_delay=5.0):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
            return resp.text
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(base_delay * attempt)
    raise last_error


def fetch_schedule_html(tournament_id, month=None):
    url = f"https://fhspb.ru/Schedule?TournamentID={tournament_id}"
    if month is not None:
        url += f"&Month={month}"
    return fetch_with_retry(url)


def clean_score(raw_score):
    if not raw_score:
        return None
    cleaned = raw_score.strip()
    empty_markers = {"", "&nbsp;", "\xa0", "-", "—"}
    if cleaned in empty_markers:
        return None
    return cleaned


def parse_matches(html):
    matches = []
    seen_ids = set()

    for m in MATCH_ROW_RE.finditer(html):
        date_str, time_str, arena, tid, match_id, teams, score = m.groups()
        if match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        team_parts = re.split(r'\s-\s', teams.strip(), maxsplit=1)
        matches.append({
            "date": date_str.strip(), "time": time_str.strip(), "arena": arena.strip(),
            "tournament_id": tid, "match_id": match_id,
            "team1": team_parts[0].strip() if len(team_parts) > 0 else None,
            "team2": team_parts[1].strip() if len(team_parts) > 1 else None,
            "score": clean_score(score),
            "protocol_url": f"https://fhspb.ru/Match?TournamentID={tid}&MatchID={match_id}",
        })

    for m in MATCH_ROW_NO_SCORE_RE.finditer(html):
        date_str, time_str, arena, tid, match_id, teams = m.groups()
        if match_id in seen_ids:
            continue
        seen_ids.add(match_id)
        team_parts = re.split(r'\s-\s', teams.strip(), maxsplit=1)
        matches.append({
            "date": date_str.strip(), "time": time_str.strip(), "arena": arena.strip(),
            "tournament_id": tid, "match_id": match_id,
            "team1": team_parts[0].strip() if len(team_parts) > 0 else None,
            "team2": team_parts[1].strip() if len(team_parts) > 1 else None,
            "score": None,
            "protocol_url": f"https://fhspb.ru/Match?TournamentID={tid}&MatchID={match_id}",
        })

    return matches


KEYCAP_DIGITS = {str(d): f"{d}\u20E3" for d in range(10)}
WEEKDAY_PREFIX_RE = re.compile(r'^[А-Яа-я]{2}\s+')
AGE_SUFFIX_RE = re.compile(r'\s+\d{1,2}(-\d{1,2})?(\s+(\d+))?$')
FULL_YEAR_SUFFIX_RE = re.compile(r'\s+(19|20)\d{2}(\s+(\d+))?$')


def score_to_keycaps(score):
    if not score:
        return ""
    parts = score.split(":")
    result = []
    for part in parts:
        part = part.strip()
        digits = "".join(KEYCAP_DIGITS.get(ch, ch) for ch in part)
        result.append(digits)
    return " : ".join(result)


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


def plain_date(date_label):
    return WEEKDAY_PREFIX_RE.sub('', date_label.strip())


def parse_match_date(date_label):
    day, month, year = plain_date(date_label).split('.')
    return datetime(int(year), int(month), int(day)).date()


GAME_DURATION = timedelta(hours=2, minutes=15)


def is_match_live(date_label, time_str):
    try:
        match_date = parse_match_date(date_label)
        hour, minute = map(int, time_str.split(':'))
        match_start = datetime(match_date.year, match_date.month, match_date.day, hour, minute)
    except (ValueError, IndexError, AttributeError):
        return False
    now = datetime.now()
    return match_start <= now <= match_start + GAME_DURATION


def is_match_probably_over(date_label, time_str):
    try:
        match_date = parse_match_date(date_label)
        hour, minute = map(int, time_str.split(':'))
        match_start = datetime(match_date.year, match_date.month, match_date.day, hour, minute)
    except (ValueError, IndexError, AttributeError):
        return False
    now = datetime.now()
    return now > match_start + GAME_DURATION


def load_spb_details_cache():
    if SPB_DETAILS_CACHE_FILE.exists():
        return json.loads(SPB_DETAILS_CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_spb_details_cache(cache):
    SPB_DETAILS_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def load_video_index():
    if VIDEO_INDEX_FILE.exists():
        return json.loads(VIDEO_INDEX_FILE.read_text(encoding="utf-8"))
    return {}


def find_video_url(date_label, team1, team2, video_index, use_rossii_key=False, age=None):
    key_fn = build_match_key_rossii if use_rossii_key else build_match_key

    if not age:
        key = key_fn(plain_date(date_label), team1, team2)
        entry = video_index.get(key)
        return entry["video_url"] if entry else None

    key_with_age = key_fn(plain_date(date_label), team1, team2, age=age)
    entry = video_index.get(key_with_age)
    if entry:
        return entry["video_url"]

    plain = plain_date(date_label)
    for other_age in ("09", "10", "11", "12", "13", "14", "15", "16", "17", "18"):
        if other_age == age:
            continue
        other_key = key_fn(plain, team1, team2, age=other_age)
        if other_key in video_index:
            return None

    key = key_fn(plain, team1, team2)
    entry = video_index.get(key)
    return entry["video_url"] if entry else None


TELEGRAM_CAPTION_LIMIT = 1024

SCORE_SUFFIX_RE = re.compile(r'(ОТ|ПБ|ТР)$')


def _breakdown_matches_score(periods_breakdown, effective_score):
    parts = SCORE_SUFFIX_RE.sub('', effective_score).split(":")
    if len(parts) != 2:
        return True
    try:
        expected = [int(parts[0]), int(parts[1])]
    except ValueError:
        return True

    totals = [0, 0]
    for period in periods_breakdown:
        for i, tg in enumerate(period.get("team_goals", [])):
            if i < 2:
                totals[i] += len(tg.get("goals", []))

    return totals == expected


def format_caption(date_label, matches, video_index, spb_lookup=None, spb_session=None,
                    spb_details_cache=None, domain="spb.fhr.ru", age=None):
    spb_lookup = spb_lookup or {}
    spb_details_cache = spb_details_cache if spb_details_cache is not None else {}

    header = date_label.upper()
    match_blocks = []

    last_group_label = None

    for m in matches:
        if m.get("group_label") and m["group_label"] != last_group_label:
            group_header = f"<b>{m['group_label']}</b>"
            match_blocks.append({"full": group_header, "compact": group_header, "spoiler_len": 0})
            last_group_label = m["group_label"]

        is_rossii_domain = spb_fhr_client is not None and domain == spb_fhr_client.KUBOK_ROSSII_DOMAIN
        video_url = find_video_url(date_label, m["team1"], m["team2"], video_index,
                                    use_rossii_key=is_rossii_domain, age=age)

        if video_url:
            team_line = f"📺 <a href=\"{video_url}\">{m['team1']} - {m['team2']}</a>"
        else:
            team_line = f"📺 {m['team1']} - {m['team2']}"

        spb_key = build_match_key(plain_date(date_label), m["team1"], m["team2"])
        spb_match = spb_lookup.get(spb_key)

        effective_score = m["score"] or (spb_match["score"] if spb_match else None)

        _direct_periods_breakdown = None
        if (not effective_score and spb_match and spb_session is not None
                and spb_fhr_client is not None and is_match_probably_over(date_label, m["time"])):
            try:
                _details = spb_fhr_client.fetch_match_live_details(spb_session, spb_match["game_id"], domain=domain)
                if _details["score"]:
                    effective_score = _details["score"]
                    _direct_periods_breakdown = _details["periods_breakdown"]
            except Exception as e:
                print(f"[WARN] Не удалось проверить страницу матча {spb_match['game_id']}: {e}")

        is_live_now = not effective_score and is_match_live(date_label, m["time"])

        live_marker = ""
        if not effective_score:
            if is_live_now:
                live_marker = " 🔴 LIVE"
            elif is_match_probably_over(date_label, m["time"]):
                live_marker = " 🟢 Матч окончен"

        time_line = f"🕐 {m['time']}{live_marker}"

        periods_breakdown = None
        live_score_line = None

        if spb_match and spb_fhr_client is not None:
            if is_live_now and spb_session is not None:
                try:
                    details = spb_fhr_client.fetch_match_live_details(spb_session, spb_match["game_id"], domain=domain)
                    if details["score"]:
                        live_score_line = details["score"]
                    periods_breakdown = details["periods_breakdown"]
                except Exception as e:
                    print(f"[WARN] Не удалось получить живые данные матча {spb_match['game_id']}: {e}")
            elif effective_score:
                cached = spb_details_cache.get(spb_match["game_id"])
                cache_is_complete = cached is not None and _breakdown_matches_score(cached, effective_score)

                if cache_is_complete:
                    periods_breakdown = cached
                elif _direct_periods_breakdown is not None:
                    periods_breakdown = _direct_periods_breakdown
                    spb_details_cache[spb_match["game_id"]] = periods_breakdown
                elif spb_session is not None:
                    try:
                        details = spb_fhr_client.fetch_match_live_details(spb_session, spb_match["game_id"], domain=domain)
                        periods_breakdown = details["periods_breakdown"]
                        spb_details_cache[spb_match["game_id"]] = periods_breakdown
                        if not _breakdown_matches_score(periods_breakdown, effective_score):
                            print(f"[INFO] Данные матча {spb_match['game_id']} пока не полностью "
                                  f"сходятся со счётом {effective_score} — сохранили как есть, "
                                  f"попробуем дополнить на следующем прогоне.")
                    except Exception as e:
                        print(f"[WARN] Не удалось получить данные завершённого матча "
                              f"{spb_match['game_id']}: {e}")
                        if cached is not None:
                            periods_breakdown = cached
                elif cached is not None:
                    periods_breakdown = cached

        live_score_line_text = f"Live-счёт: {live_score_line}" if live_score_line else None

        spoiler_block = None
        if periods_breakdown:
            spoiler_lines = []
            for period in periods_breakdown:
                period_label = period.get("label") or f"{period.get('period_number', '?')}-й период"
                spoiler_lines.append(f"{period_label} ({period['score']}):")
                for tg in period["team_goals"]:
                    if tg["goals"]:
                        spoiler_lines.append(f"  {tg['name']}:")
                        for g in tg["goals"]:
                            spoiler_lines.append(f"    {g['number']}.{g['player']} {g['minute']}'")
                spoiler_lines.append("")

            spoiler_text = "\n".join(spoiler_lines).rstrip()
            spoiler_block = f"<blockquote expandable>{spoiler_text}</blockquote>"

        result_lines = []
        if effective_score:
            result_lines.append(f"Итог матча: {score_to_keycaps(effective_score)}")
            protocol_link = spb_match["game_url"] if spb_match else m["protocol_url"]
            result_lines.append(f"<a href=\"{protocol_link}\">Протокол матча</a>")

        common_lines = [team_line, time_line]
        if live_score_line_text:
            common_lines.append(live_score_line_text)

        full_lines = common_lines + ([spoiler_block] if spoiler_block else []) + result_lines
        compact_lines = common_lines + result_lines

        match_blocks.append({
            "full": "\n".join(full_lines),
            "compact": "\n".join(compact_lines),
            "spoiler_len": len(spoiler_block) if spoiler_block else 0,
        })

    def _assemble(blocks_text):
        return "\n".join([header, ""] + [b + "\n" for b in blocks_text]).strip()

    versions = [b["full"] for b in match_blocks]
    caption = _assemble(versions)

    if len(caption) > TELEGRAM_CAPTION_LIMIT:
        order = sorted(range(len(match_blocks)), key=lambda i: match_blocks[i]["spoiler_len"], reverse=True)
        for idx in order:
            if len(caption) <= TELEGRAM_CAPTION_LIMIT:
                break
            if match_blocks[idx]["spoiler_len"] == 0:
                continue
            versions[idx] = match_blocks[idx]["compact"]
            caption = _assemble(versions)

    return caption


def get_banner_path(age, group, tournament_type):
    group_letter_map = {"A": "a", "А": "a", "B": "b", "Б": "b"}
    group_suffix = f"_group{group_letter_map.get(group, '')}" if group else ""
    type_suffix = "cup" if tournament_type == "КУБОК" else "champ"
    filename = f"{age}{group_suffix}_{type_suffix}.png"
    return BANNERS_DIR / filename


def send_photo(topic_id, banner_path, caption):
    with open(banner_path, "rb") as photo_file:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto",
            data={"chat_id": TG_CHAT_ID, "message_thread_id": topic_id,
                  "caption": caption, "parse_mode": "HTML",
                  "disable_notification": True},
            files={"photo": photo_file}, timeout=30,
        )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendPhoto error: {data}")
    return data["result"]["message_id"]


def edit_caption(message_id, caption):
    resp = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageCaption",
        data={"chat_id": TG_CHAT_ID, "message_id": message_id,
              "caption": caption, "parse_mode": "HTML"}, timeout=30,
    )
    data = resp.json()
    if not data.get("ok") and "message is not modified" not in str(data.get("description", "")):
        raise RuntimeError(f"Telegram editMessageCaption error: {data}")


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _acquire_lock():
    if LOCK_FILE.exists():
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            os.kill(old_pid, 0)
            return False
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))
    return True


def _release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def process_tournament(age, group, tournament_type, tournament_id, state, video_index, dry_run,
                        official_keys=None, month=None, spb_session=None, spb_details_cache=None):
    topic_id = TOPIC_IDS[age]

    html = fetch_schedule_html(tournament_id, month=month)
    matches = parse_matches(html)

    if not matches:
        return

    if official_keys is not None:
        for m in matches:
            key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
            official_keys.add(key)

    spb_lookup = {}
    if (spb_session is not None and spb_fhr_client is not None
            and tournament_type == "КУБОК" and age in spb_fhr_client.KUBOK_SPB_YEAR_IDS):
        try:
            spb_matches = spb_fhr_client.fetch_calendar_matches(
                spb_session, spb_fhr_client.KUBOK_SPB_TOURNAMENT_ID,
                spb_fhr_client.KUBOK_SPB_YEAR_IDS[age],
            )
            for sm in spb_matches:
                key = build_match_key(sm["date"], sm["team1"], sm["team2"])
                spb_lookup[key] = {"game_id": sm["game_id"], "game_url": sm["game_url"],
                                    "score": sm["score"]}
        except Exception as e:
            print(f"[WARN] spb.fhr.ru недоступен для {age} г.р. КУБОК: {e}")

    banner_path = get_banner_path(age, group, tournament_type)
    if not banner_path.exists():
        print(f"[WARN] Баннер не найден: {banner_path} — пропускаю {age}/{group}/{tournament_type}")
        return

    by_date = {}
    for m in matches:
        by_date.setdefault(m["date"], []).append(m)

    for date_label, day_matches in by_date.items():
        state_key = f"{tournament_id}_{date_label}"
        caption = format_caption(date_label, day_matches, video_index, spb_lookup, spb_session,
                                  spb_details_cache, age=age[-2:])

        existing = state.get(state_key)

        if existing is None:
            try:
                match_date = parse_match_date(date_label)
                days_until = (match_date - datetime.now().date()).days
            except (ValueError, IndexError):
                days_until = 0

            if days_until > 1:
                continue

            print(f"\n[НОВЫЙ ПОСТ] {age} г.р. {group or ''} {tournament_type} — {date_label}")
            print(caption)
            if not dry_run:
                message_id = send_photo(topic_id, banner_path, caption)
                state[state_key] = {"message_id": message_id, "caption": caption}
                save_state(state)
                time.sleep(1)
            else:
                print("  (dry-run — не отправлено)")
        else:
            if existing.get("caption") != caption:
                print(f"\n[ОБНОВЛЕНИЕ] {age} г.р. {group or ''} {tournament_type} — {date_label}")
                print(caption)
                if not dry_run:
                    edit_caption(existing["message_id"], caption)
                    existing["caption"] = caption
                    save_state(state)
                    time.sleep(1)
                else:
                    print("  (dry-run — не отредактировано)")


KUBOK_ROSSII_BANNER = BANNERS_DIR / "2011_kubokrossii.png"


def process_kubok_rossii(state, dry_run, spb_rossii_session=None, official_keys=None, spb_details_cache=None,
                          video_index=None):
    if spb_fhr_client is None or spb_rossii_session is None:
        return

    age = "2011"
    topic_id = TOPIC_IDS[age]

    try:
        rossii_matches = spb_fhr_client.fetch_kubok_rossii_matches(spb_rossii_session)
    except Exception as e:
        print(f"[WARN] Кубок России недоступен: {e}")
        return

    if not rossii_matches:
        return

    rossii_teams = sorted({t for rm in rossii_matches for t in (rm["team1"], rm["team2"])})
    KUBOK_ROSSII_TEAMS_FILE.write_text(
        json.dumps(rossii_teams, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    matches = []
    spb_lookup = {}
    for rm in rossii_matches:
        m = {
            "date": rm["date"], "time": rm["time"], "arena": "",
            "team1": rm["team1"], "team2": rm["team2"],
            "score": rm["score"], "protocol_url": rm["game_url"],
            "group_label": rm.get("group"),
        }
        matches.append(m)

        key = build_match_key(plain_date(m["date"]), m["team1"], m["team2"])
        if official_keys is not None:
            official_keys.add(key)
        spb_lookup[key] = {"game_id": rm["game_id"], "game_url": rm["game_url"], "score": rm["score"]}

    if not KUBOK_ROSSII_BANNER.exists():
        print(f"[WARN] Баннер не найден: {KUBOK_ROSSII_BANNER} — пропускаю Кубок России")
        return

    by_date = {}
    for m in matches:
        by_date.setdefault(m["date"], []).append(m)

    group_order = {name: i for i, name in enumerate(spb_fhr_client.KUBOK_ROSSII_GROUP_IDS.keys())}
    for day_matches in by_date.values():
        day_matches.sort(key=lambda m: group_order.get(m.get("group_label"), 999))

    for date_label, day_matches in by_date.items():
        state_key = f"kubokrossii_{date_label}"
        caption = format_caption(date_label, day_matches, video_index or {}, spb_lookup, spb_rossii_session,
                                  spb_details_cache, domain=spb_fhr_client.KUBOK_ROSSII_DOMAIN, age=age[-2:])

        existing = state.get(state_key)

        if existing is None:
            try:
                match_date = parse_match_date(date_label)
                days_until = (match_date - datetime.now().date()).days
            except (ValueError, IndexError):
                days_until = 0

            if days_until > 1:
                continue

            print(f"\n[НОВЫЙ ПОСТ] {age} г.р. КУБОК РОССИИ — {date_label}")
            print(caption)
            if not dry_run:
                message_id = send_photo(topic_id, KUBOK_ROSSII_BANNER, caption)
                state[state_key] = {"message_id": message_id, "caption": caption}
                save_state(state)
                time.sleep(1)
            else:
                print("  (dry-run — не отправлено)")
        else:
            if existing.get("caption") != caption:
                print(f"\n[ОБНОВЛЕНИЕ] {age} г.р. КУБОК РОССИИ — {date_label}")
                print(caption)
                if not dry_run:
                    edit_caption(existing["message_id"], caption)
                    existing["caption"] = caption
                    save_state(state)
                    time.sleep(1)
                else:
                    print("  (dry-run — не отредактировано)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-last-season", action="store_true")
    args = parser.parse_args()

    if not args.live and not args.dry_run:
        print("Укажите --dry-run (тест) или --live (реальная отправка)")
        sys.exit(1)

    if not _acquire_lock():
        print("[INFO] Предыдущий прогон, судя по всему, ещё выполняется — пропускаем этот запуск.")
        return

    try:
        _run(args)
    finally:
        _release_lock()


def _run(args):
    dry_run = not args.live
    state = load_state()
    video_index = load_video_index()
    official_keys = set()
    spb_details_cache = load_spb_details_cache()

    spb_session = None
    if spb_fhr_client is not None:
        try:
            spb_session = spb_fhr_client.create_session()
        except Exception as e:
            print(f"[WARN] Не удалось создать сессию spb.fhr.ru, продолжаем без обогащения: {e}")

    spb_rossii_session = None
    if spb_fhr_client is not None:
        try:
            spb_rossii_session = spb_fhr_client.create_session_kubok_rossii()
        except Exception as e:
            print(f"[WARN] Не удалось создать сессию junior.fhr.ru (Кубок России): {e}")

    if args.test_last_season:
        print("=== ТЕСТОВЫЙ ПРОГОН НА ДАННЫХ ПРОШЛОГО СЕЗОНА (TournamentID=6367) ===")
        process_tournament("2011", "Б", "ПЕРВЕНСТВО", 6367, state, video_index, dry_run=True)
        return

    for age, tournament_id in CUP_CONFIG.items():
        try:
            process_tournament(age, None, "КУБОК", tournament_id, state, video_index, dry_run,
                                official_keys=official_keys, spb_session=spb_session,
                                spb_details_cache=spb_details_cache)
        except Exception as e:
            print(f"[ERROR] {age}/КУБОК: {e}")
        time.sleep(4)

    try:
        process_kubok_rossii(state, dry_run, spb_rossii_session=spb_rossii_session,
                              official_keys=official_keys, spb_details_cache=spb_details_cache,
                              video_index=video_index)
    except Exception as e:
        print(f"[ERROR] Кубок России: {e}")

    for age, group, tournament_id in CHAMPIONSHIP_CONFIG:
        try:
            process_tournament(age, group, "ПЕРВЕНСТВО", tournament_id, state, video_index, dry_run,
                                official_keys=official_keys)
        except Exception as e:
            print(f"[ERROR] {age}/{group}/ПЕРВЕНСТВО: {e}")
        time.sleep(4)

    OFFICIAL_MATCHES_FILE.write_text(
        json.dumps(sorted(official_keys), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nСписок официальных матчей сохранён: {len(official_keys)} записей")

    save_spb_details_cache(spb_details_cache)
    print(f"Кэш деталей spb.fhr.ru: {len(spb_details_cache)} завершённых матчей")

    print("\nГотово.")


if __name__ == "__main__":
    main()
