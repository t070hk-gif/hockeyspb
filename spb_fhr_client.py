#!/usr/bin/env python3
"""
Клиент для сайтов spb.fhr.ru (Кубок СПБ) и junior.fhr.ru (Кубок России) —
Федерация хоккея России, дополнительный источник данных к fhspb.ru.

КЛЮЧЕВЫЕ ОСОБЕННОСТИ (важно для понимания кода):
1. Оба сайта защищены Yandex SmartCaptcha в фоновом режиме — обычные
   GET-запросы проходят, если сначала получена валидная Bitrix-сессия.
2. Страницы отдельных матчей содержат счёт, счёт по периодам, авторов шайб.
3. Список игр — через AJAX-эндпоинт Bitrix D7. base64-параметры ОБЯЗАТЕЛЬНО
   URL-кодировать отдельно (urllib.parse.quote) — иначе сервер молча
   вернёт контент по умолчанию.
4. spb.fhr.ru и junior.fhr.ru используют РАЗНУЮ разметку строки таблицы
   расписания (см. ROW_RE и ROSSII_ROW_RE) — junior.fhr.ru к тому же
   разбивает Кубок России на группы, а не на возраста.
5. Заголовок страницы в AJAX-ответе НЕ обновляется (баг сайта) — данные
   матчей при этом фильтруются правильно.
"""

import base64
import re
import time
import urllib.parse
from datetime import datetime

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                  "(KHTML, like Gecko) Version/18.6 Safari/605.1.15",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru",
}

KUBOK_SPB_TOURNAMENT_ID = "24813595"

KUBOK_SPB_YEAR_IDS = {
    "2010": "24813596",
    "2011": "24813599",
    "2012": "24813600",
    "2013": "24813601",
    "2014": "24813602",
    "2015": "24813603",  # не подтверждено, стабильно возвращает 500
}

KUBOK_ROSSII_DOMAIN = "junior.fhr.ru"
KUBOK_ROSSII_TOURNAMENT_SLUG = "kubokrossii-25008909"
KUBOK_ROSSII_TOURNAMENT_ID = "25008909"
KUBOK_ROSSII_YEAR_ID = "25008950"
KUBOK_ROSSII_GROUP_IDS = {
    "Группа А-I": "25169259",
    "Группа Б-I": "25169381",
    "Группа В-I": "25008978",  # подтверждено с сайта (ранее ошибочно было "Г")
    "Группа Г-I": "25169384",  # подтверждено с сайта (ранее ошибочно было "В")
}

AJAX_COMPONENT_PATH = (
    "SXRwcm9maXRcQXBwXEFqYXhcQWpheENvbXBvbmVudA==/cmVuZGVyQ29tcG9uZW50"
)

ROW_RE = re.compile(
    r'<tr onclick="location\.href=onlick=location\.href=\'/games/(\d+)/\'">(.*?)</tr>',
    re.DOTALL,
)
DATE_RE = re.compile(r'<span class="date">\s*([\d.]+)\s*</span>')
TIME_RE = re.compile(r'<span class="time">\s*([\d:]+)\s*</span>')
TEAM_RE = re.compile(r'<span class="team-title">\s*(.*?)\s*</span>', re.DOTALL)
SCORE_RE = re.compile(r'<div class="cell score">\s*(.*?)\s*</div>', re.DOTALL)

ROSSII_ROW_RE = re.compile(r'<tr>\s*(.*?)</tr>', re.DOTALL)
ROSSII_GAME_ID_RE = re.compile(r'/games/(\d+)/')
ROSSII_DATE_RE = re.compile(r'<span class="date">\s*([\d.]+)\s*</span>')
ROSSII_TIME_RE = re.compile(r'<span class="time">\s*([\d:]+)')
ROSSII_TEAM_RE = re.compile(r'<span class="team-title">\s*(.*?)\s*</span>', re.DOTALL)
ROSSII_SCORE_RE = re.compile(r'<div class="cell score bold">\s*(.*?)\s*</div>', re.DOTALL)

MATCH_SCORE_RE = re.compile(
    r'<span class="match-score">\s*<span class="text-score">(\d+)</span>\s*'
    r'<span class="score-separator">:</span>\s*<span class="text-score">(\d+)</span>',
    re.DOTALL,
)
PERIOD_SCORE_RE = re.compile(
    r'<div class="period-score">\s*<span class="text-score">(\d+)</span>\s*'
    r'<span class="score-separator">:</span>\s*<span class="text-score">(\d+)</span>',
    re.DOTALL,
)
GOAL_RE = re.compile(r'(\d+)\.([^<]+?)\s+(\d+)’')
TEAM_BLOCK_RE = re.compile(
    r'class="(?:first|second)-team team-block">.*?'
    r'<span class="team-title">\s*(.*?)\s*</span>.*?'
    r'<ul class="team-players">(.*?)</ul>',
    re.DOTALL,
)


def _get_with_retry(session, url, max_attempts=4, base_delay=3.0, **kwargs):
    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            resp = session.get(url, timeout=25, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_error = e
            if attempt < max_attempts:
                time.sleep(base_delay * attempt)
    raise last_error


def create_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    _get_with_retry(
        session,
        f"https://spb.fhr.ru/tournaments/kubok-spb-{KUBOK_SPB_TOURNAMENT_ID}/",
    )
    return session


def create_session_kubok_rossii():
    session = requests.Session()
    session.headers.update(HEADERS)
    _get_with_retry(
        session,
        f"https://{KUBOK_ROSSII_DOMAIN}/tournaments/{KUBOK_ROSSII_TOURNAMENT_SLUG}/",
    )
    return session


def fetch_calendar_matches(session, tournament_id, year_id, domain="spb.fhr.ru", group_id=None):
    group_part = f's:8:"{group_id}"' if group_id else "N"
    php_params = (
        f'a:4:{{s:13:"TOURNAMENT_ID";s:8:"{tournament_id}";s:8:"GROUP_ID";{group_part};'
        f's:7:"YEAR_ID";s:8:"{year_id}";s:7:"is_ajax";b:1;}}'
    )
    params_b64 = base64.b64encode(php_params.encode()).decode()
    params_encoded = urllib.parse.quote(params_b64, safe="")

    referer = f"https://{domain}/tournaments/kubok-spb-{tournament_id}/" if domain == "spb.fhr.ru" \
        else f"https://{domain}/tournaments/{KUBOK_ROSSII_TOURNAMENT_SLUG}/"

    url = (
        f"https://{domain}/fhr-ajax/{AJAX_COMPONENT_PATH}/"
        f"?component=itprofit%3Acompetitions-calendar&template=.default"
        f"&params={params_encoded}"
    )

    resp = _get_with_retry(session, url, headers={"Referer": referer})
    html = resp.text

    is_rossii = domain == KUBOK_ROSSII_DOMAIN
    row_re = ROSSII_ROW_RE if is_rossii else ROW_RE
    date_re = ROSSII_DATE_RE if is_rossii else DATE_RE
    time_re = ROSSII_TIME_RE if is_rossii else TIME_RE
    team_re = ROSSII_TEAM_RE if is_rossii else TEAM_RE
    score_re = ROSSII_SCORE_RE if is_rossii else SCORE_RE

    matches = []
    for m in row_re.finditer(html):
        block = m.group(1) if not is_rossii else m.group(0)
        if is_rossii:
            game_id_m = ROSSII_GAME_ID_RE.search(block)
            if not game_id_m:
                continue
            game_id = game_id_m.group(1)
        else:
            game_id, block = m.groups()

        date_m = date_re.search(block)
        time_m = time_re.search(block)
        teams = team_re.findall(block)
        score_m = score_re.search(block)

        team1 = teams[0].strip() if len(teams) > 0 else ""
        team2 = teams[1].strip() if len(teams) > 1 else ""
        if not team1 or not team2:
            continue

        raw_score = score_m.group(1).strip() if score_m else ""
        score = raw_score if raw_score and raw_score != ":" else None

        matches.append({
            "game_id": game_id,
            "date": date_m.group(1) if date_m else None,
            "time": time_m.group(1) if time_m else None,
            "team1": team1,
            "team2": team2,
            "score": score,
            "game_url": f"https://{domain}/games/{game_id}/",
        })

    return matches


def fetch_kubok_rossii_matches(session):
    all_matches = []
    for group_name, group_id in KUBOK_ROSSII_GROUP_IDS.items():
        try:
            group_matches = fetch_calendar_matches(
                session, KUBOK_ROSSII_TOURNAMENT_ID, KUBOK_ROSSII_YEAR_ID,
                domain=KUBOK_ROSSII_DOMAIN, group_id=group_id,
            )
            for m in group_matches:
                m["group"] = group_name
            all_matches.extend(group_matches)
        except Exception as e:
            print(f"[WARN] Кубок России, {group_name}: не удалось получить расписание: {e}")
        time.sleep(1.5)
    return all_matches


def _period_label(period_index):
    if period_index <= 3:
        return f"{period_index}-й период"
    if period_index == 4:
        return "Овертайм"
    if period_index == 5:
        return "Буллиты"
    return f"{period_index}-й период"


def _bucket_goals_by_period(periods, teams):
    remaining_goals = [list(t["goals"]) for t in teams]
    result = []

    for i, period_score in enumerate(periods, start=1):
        parts = period_score.split(":")
        if len(parts) != 2:
            continue
        try:
            counts = [int(parts[0]), int(parts[1])]
        except ValueError:
            continue

        period_team_goals = []
        has_goals = False
        for team_idx, team in enumerate(teams):
            count = counts[team_idx] if team_idx < len(counts) else 0
            taken, remaining_goals[team_idx] = (
                remaining_goals[team_idx][:count],
                remaining_goals[team_idx][count:],
            )
            if taken:
                has_goals = True
            period_team_goals.append({"name": team["name"], "goals": taken})

        if has_goals:
            result.append({
                "period_number": i,
                "label": _period_label(i),
                "score": period_score,
                "team_goals": period_team_goals,
            })

    return result


def fetch_match_live_details(session, game_id, domain="spb.fhr.ru"):
    referer = f"https://{domain}/tournaments/kubok-spb-{KUBOK_SPB_TOURNAMENT_ID}/" \
        if domain == "spb.fhr.ru" else f"https://{domain}/tournaments/{KUBOK_ROSSII_TOURNAMENT_SLUG}/"
    url = f"https://{domain}/games/{game_id}/"
    resp = _get_with_retry(session, url, headers={"Referer": referer})
    html = resp.text

    result = {"score": None, "periods": [], "teams": [], "periods_breakdown": []}

    score_m = MATCH_SCORE_RE.search(html)
    if score_m:
        result["score"] = f"{score_m.group(1)}:{score_m.group(2)}"

    for p in PERIOD_SCORE_RE.finditer(html):
        result["periods"].append(f"{p.group(1)}:{p.group(2)}")

    for team_name, players_block in TEAM_BLOCK_RE.findall(html):
        goals = [
            {"number": number, "player": player.strip(), "minute": minute}
            for number, player, minute in GOAL_RE.findall(players_block)
        ]
        result["teams"].append({"name": team_name.strip(), "goals": goals})

    result["periods_breakdown"] = _bucket_goals_by_period(result["periods"], result["teams"])

    return result


if __name__ == "__main__":
    session = create_session()
    matches = fetch_calendar_matches(session, KUBOK_SPB_TOURNAMENT_ID, KUBOK_SPB_YEAR_IDS["2013"])
    for m in matches:
        score_str = m["score"] or "—"
        print(f"{m['date']} {m['time']} | {m['team1']} vs {m['team2']} | {score_str} | {m['game_url']}")
