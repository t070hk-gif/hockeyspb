#!/usr/bin/env python3
"""
Бот турнирных таблиц: тянет уже посчитанную турнирную таблицу с fhspb.ru
(Standings) для каждого турнира и публикует/обновляет один пост в
соответствующей теме Telegram-группы. Таблица идёт как обычный текст
(моноширинный <pre> формат) — не как фото с баннером, так как это
плотная табличная информация, а не анонс конкретной игры.

РЕЖИМЫ ЗАПУСКА:
    python3 post_standings.py --dry-run          # только показать, без отправки
    python3 post_standings.py --live               # реальная отправка
    python3 post_standings.py --dry-run --test-last-season
                                                     # прогон на прошлогоднем турнире

Логика обновления: для каждого турнира храним message_id последнего поста
с таблицей. При каждом запуске сверяем текст новой таблицы с сохранённым —
если отличается (кто-то сыграл матч, изменились очки/место), редактируем
существующий пост вместо создания нового.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

TG_BOT_TOKEN = "7972710769:AAGA1FQ1_Sh7K2EtTvCvzji-SJPxZ-kp_54"
TG_CHAT_ID = -1002723611949  # ВСЕССЫЛКИ.СПБ

STATE_FILE = Path(__file__).parent / "standings_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

TOPIC_IDS = {
    "2009": 3, "2010": 5, "2011": 8, "2012": 9, "2013": 10,
    "2014": 11, "2015": 104, "2016": 105, "2017": 106, "2018": 868,
}

# Примечание: Кубок СПб турнирную таблицу не публикуем (по решению
# администратора) — только Первенство СПб. Расписание/результаты Кубка
# по-прежнему ведутся отдельным ботом post_schedule.py.

# Первенство СПб: делится по возрастам И группам А/Б (кроме 2009, 2010)
CHAMPIONSHIP_CONFIG = [
    ("2009", None, 6571),
    ("2010", None, 6572),
    ("2011", "A", 6573),
    ("2011", "Б", 6574),
    ("2012", "A", 6575),
    ("2012", "Б", 6576),
    ("2013", "A", 6577),
    ("2013", "Б", 6578),
    ("2014", "A", 6579),
    ("2014", "Б", 6580),
    ("2015", "A", 6581),
    ("2015", "Б", 6582),
]



# ------------------- ПАРСИНГ ТУРНИРНОЙ ТАБЛИЦЫ (fhspb.ru) -------------------

TEAM_NAME_RE = re.compile(r'<a href="Team\.aspx\?TournamentID=\d+&amp;TeamID=[^"]+">([^<]+)</a>')
PLAIN_CELL_RE = re.compile(r'<td align="center"[^>]*>([^<]+)</td>')


def fetch_with_retry(url: str, max_attempts: int = 4, base_delay: float = 3.0) -> str:
    """
    fhspb.ru периодически обрывает соединение при частых последовательных
    запросах — повторяем попытку с увеличивающейся паузой перед тем,
    как сдаться (та же логика, что и в post_schedule.py).
    """
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


def fetch_standings_html(tournament_id: int) -> str:
    url = f"https://fhspb.ru/Standings?TournamentID={tournament_id}"
    return fetch_with_retry(url)


def parse_standings(html: str) -> list:
    table_match = re.search(
        r'<table class="standings"[^>]*id="StandingsGridView"[^>]*>(.*?)</table>',
        html, re.DOTALL,
    )
    if not table_match:
        return []

    table_html = table_match.group(1)
    rows = re.split(r'</tr>\s*<tr>', table_html)
    rows = [r for r in rows if 'Team.aspx' in r]

    standings = []
    for row in rows:
        team_match = TEAM_NAME_RE.search(row)
        plain_cells = PLAIN_CELL_RE.findall(row)

        if not team_match or len(plain_cells) < 8:
            continue

        rank, games, wins, draws, losses, goal_diff, penalty, points = plain_cells[-8:]

        standings.append({
            "rank": int(rank),
            "team": team_match.group(1).strip(),
            "games": int(games),
            "wins": int(wins),
            "draws": int(draws),
            "losses": int(losses),
            "goal_diff": goal_diff.strip(),
            "penalty": int(penalty),
            "points": int(points),
        })

    standings.sort(key=lambda t: t["rank"])
    return standings


def format_standings_message(age: str, group: str, tournament_type: str, standings: list) -> str:
    group_label = f" Группа {group}" if group else ""
    title = f"🏆 {tournament_type} СПБ {age} г.р.{group_label}"

    header = f"{'#':>2} {'Команда':<20} {'И':>3} {'В':>3} {'П':>3} {'О':>3}"
    sep = "-" * len(header)

    rows = []
    for t in standings:
        team_name = t["team"][:20]
        rows.append(
            f"{t['rank']:>2} {team_name:<20} {t['games']:>3} {t['wins']:>3} "
            f"{t['losses']:>3} {t['points']:>3}"
        )

    table_text = "\n".join([header, sep] + rows)
    return f"{title}\n\n<pre>{table_text}</pre>"


# ------------------- TELEGRAM -------------------

def send_message(topic_id: int, text: str) -> int:
    resp = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
        data={
            "chat_id": TG_CHAT_ID,
            "message_thread_id": topic_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_notification": True,
        },
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage error: {data}")
    return data["result"]["message_id"]


def edit_message(message_id: int, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{TG_BOT_TOKEN}/editMessageText",
        data={
            "chat_id": TG_CHAT_ID,
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
        },
        timeout=30,
    )
    data = resp.json()
    if not data.get("ok") and "message is not modified" not in str(data.get("description", "")):
        raise RuntimeError(f"Telegram editMessageText error: {data}")


# ------------------- СОСТОЯНИЕ -------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ------------------------- ОСНОВНАЯ ЛОГИКА -------------------------

def process_tournament(age: str, group: str, tournament_type: str, tournament_id: int,
                        state: dict, dry_run: bool) -> None:
    topic_id = TOPIC_IDS[age]

    html = fetch_standings_html(tournament_id)
    standings = parse_standings(html)

    if not standings:
        return  # турнир ещё не начался / нет данных

    text = format_standings_message(age, group, tournament_type, standings)
    state_key = str(tournament_id)
    existing = state.get(state_key)

    if existing is None:
        print(f"\n[НОВАЯ ТАБЛИЦА] {age} г.р. {group or ''} {tournament_type}")
        print(text)
        if not dry_run:
            message_id = send_message(topic_id, text)
            state[state_key] = {"message_id": message_id, "text": text}
            save_state(state)
            time.sleep(1)
        else:
            print("  (dry-run — не отправлено)")
    else:
        if existing["text"] != text:
            print(f"\n[ОБНОВЛЕНИЕ ТАБЛИЦЫ] {age} г.р. {group or ''} {tournament_type}")
            print(text)
            if not dry_run:
                edit_message(existing["message_id"], text)
                existing["text"] = text
                save_state(state)
                time.sleep(1)
            else:
                print("  (dry-run — не отредактировано)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-last-season", action="store_true",
                         help="Тестовый прогон на TournamentID прошлого сезона (6367)")
    args = parser.parse_args()

    if not args.live and not args.dry_run:
        print("Укажите --dry-run (тест) или --live (реальная отправка)")
        sys.exit(1)

    dry_run = not args.live
    state = load_state()

    if args.test_last_season:
        print("=== ТЕСТОВЫЙ ПРОГОН НА ДАННЫХ ПРОШЛОГО СЕЗОНА (TournamentID=6367) ===")
        process_tournament("2011", "Б", "ПЕРВЕНСТВО", 6367, state, dry_run=True)
        return

    # Турнирную таблицу ведём ТОЛЬКО для Первенства СПб.
    # Кубок СПб — короткий отборочный этап, официальную турнирную таблицу
    # для него не публикуем (только расписание/результаты через post_schedule.py).
    for age, group, tournament_id in CHAMPIONSHIP_CONFIG:
        try:
            process_tournament(age, group, "ПЕРВЕНСТВО", tournament_id, state, dry_run)
        except Exception as e:
            print(f"[ERROR] {age}/{group}/ПЕРВЕНСТВО: {e}")
        time.sleep(2.5)

    print("\nГотово.")


if __name__ == "__main__":
    main()
