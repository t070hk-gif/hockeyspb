#!/usr/bin/env python3
"""
Скачивает официальные списки команд с сайта ФХСПб для каждой возрастной
группы и сохраняет в teams.json.

Согласно Регламенту ФХСПб на сезон 2026-2027 (раздел 3.6-3.9), для
возрастов 2010-2015 г.р. проводится ДВА турнира подряд — сначала Кубок
Санкт-Петербурга, затем Первенство. Скрипт объединяет команды из обоих.
"""

import json
import re
import time
from pathlib import Path

import requests

TOURNAMENTS = {
    "2009": [6571],
    "2010": [6565, 6572],
    "2011-А": [6566, 6573],
    "2011-Б": [6566, 6574],
    "2012-А": [6567, 6575],
    "2012-Б": [6567, 6576],
    "2013-А": [6568, 6577],
    "2013-Б": [6568, 6578],
    "2014-А": [6569, 6579],
    "2014-Б": [6569, 6580],
    "2015-А": [6570, 6581],
    "2015-Б": [6570, 6582],
    "2016": [6583],
    "2017": [6584],
    "2018": [6585],
}

TEAM_RE = re.compile(r'<h5><a href="Team\.aspx\?TournamentID=\d+&TeamID=[^"]+">([^<]+)</a></h5>')

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

OUTPUT_FILE = Path(__file__).parent / "teams.json"


def fetch_teams_for_tournament(tournament_id: int) -> list:
    url = f"https://fhspb.ru/Tournament?TournamentID={tournament_id}"
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return TEAM_RE.findall(resp.text)


def main():
    result = {}

    for age_group, tournament_ids in TOURNAMENTS.items():
        combined_teams = []
        seen = set()

        for tournament_id in tournament_ids:
            try:
                teams = fetch_teams_for_tournament(tournament_id)
                new_count = 0
                for t in teams:
                    if t not in seen:
                        seen.add(t)
                        combined_teams.append(t)
                        new_count += 1
                print(f"  TournamentID={tournament_id}: {len(teams)} команд ({new_count} новых)")
            except Exception as e:
                print(f"  TournamentID={tournament_id}: ошибка — {e}")

            time.sleep(1)

        print(f"✅ {age_group} г.р.: итого {len(combined_teams)} уникальных команд")
        for t in combined_teams:
            print(f"     - {t}")
        result[age_group] = combined_teams
        print()

    OUTPUT_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Сохранено в {OUTPUT_FILE}")

    total_teams = sum(len(v) for v in result.values())
    print(f"Всего команд по всем группам: {total_teams}")


if __name__ == "__main__":
    main()
