#!/usr/bin/env python3
"""
Ревизия: какие официальные матчи остались без видео, и поиск трансляций
для них несколькими способами — от строгого к мягкому.

  4 строгое          — как работает бот (team_matcher)
  3 по названиям     — обе команды упомянуты в любой форме, дата совпадает
  2 команда + время  — одна команда в заголовке, начало трансляции ±45 мин
  1 время + группа   — безликий заголовок, начало ±15 мин, группа раньше
                       транслировала игры одной из этих команд

    python3 audit_missing_videos.py              — только отчёт (7 дней назад + завтра)
    python3 audit_missing_videos.py --apply      — записать надёжные находки
    python3 audit_missing_videos.py --days 14    — другой период

Записывается только надёжное: способы 3–4, способ 2 при расхождении
времени до 20 мин, и только если кандидат единственный и не претендует на
другой матч. Существующие ссылки не перезаписываются.
"""
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, ".")
import vk_to_tg_hockey_bot as bot
import team_matcher as tm

METHODS = {4: "строгое", 3: "по названиям", 2: "команда+время", 1: "время+группа"}


def parse_args():
    days = 7
    if "--days" in sys.argv:
        days = int(sys.argv[sys.argv.index("--days") + 1])
    return "--apply" in sys.argv, days


def hints(title, owner):
    f = getattr(bot, "_apply_group_hints", None)
    return f(title, owner) if f else title


def main():
    apply, days = parse_args()
    today = datetime.now().date()
    dates = [(today - timedelta(days=k)).strftime("%d.%m.%Y") for k in range(days, -2, -1)]

    fixtures = tm.load_fixtures()
    aliases = tm.load_alias_groups()
    index = bot.load_video_index()

    used, group_history = set(), defaultdict(set)
    for key, entry in index.items():
        m = re.search(r"video(-?\d+)_(\d+)", entry.get("video_url", ""))
        if not m:
            continue
        used.add(f"{m.group(1)}_{m.group(2)}")
        parts = key.split("::")
        if len(parts) > 1 and "|" in parts[1]:
            group_history[int(m.group(1))].update(parts[1].split("|"))

    # Привязанным считаем только видео под ключом настоящего официального
    # матча — записанное старой логикой под неверным ключом проверяем снова.
    if hasattr(bot, "_registered_video_ids"):
        used = bot._registered_video_ids()

    def has_video(fx):
        if fx.get("age") and f'{fx["key"]}::{fx["age"]}' in index:
            return True
        if fx["key"] in index:
            rivals = [f for f in fixtures.get(fx["date"], [])
                      if f["key"] == fx["key"] and f.get("age") != fx.get("age")]
            return not rivals   # общий ключ без возраста — только если пара играет в один возраст
        return False

    missing = [fx for d in dates for fx in fixtures.get(d, []) if not has_video(fx)]
    total = sum(len(fixtures.get(d, [])) for d in dates)
    print(f"Период {dates[0]} – {dates[-1]}: официальных матчей {total}, без видео {len(missing)}")
    if not missing:
        return

    print("Загружаю видео групп VK…")
    tokens, _ = bot.load_tokens(), None
    token, _ = bot.get_valid_access_token(tokens)
    videos = []
    for gid in bot.VK_GROUP_IDS:
        try:
            for v in bot.vk_get_group_videos(token, gid, count=100) or []:
                full_id = f'{v["owner_id"]}_{v["id"]}'
                title = v.get("title", "")
                if full_id in used or any(w in title.lower() for w in tm.REVIEW_WORDS):
                    continue
                th = hints(title, v["owner_id"])
                toks, ages = tm.tokenize_title(th)
                live = v.get("live_start_time")
                videos.append({
                    "full_id": full_id, "owner": v["owner_id"], "title": title, "th": th,
                    "tokens": toks, "age": ages[0] if len(set(ages)) == 1 else None,
                    "dates": set(tm.build_date_candidates(th, live, v.get("date"), window=1)),
                    "start": datetime.fromtimestamp(live) if live else None,
                })
        except Exception as e:
            print(f"  группа {gid}: ошибка {e}")
        time.sleep(1.2)
    print(f"Не привязанных видео для поиска: {len(videos)}\n")

    cands = defaultdict(list)          # индекс матча -> [(сила, Δмин, видео)]
    for i, fx in enumerate(missing):
        for v in videos:
            if v["age"] and fx.get("age") and v["age"] != fx["age"]:
                continue
            diff = tm._minutes_from(fx, v["start"]) if v["start"] else float("inf")
            m1 = tm.mentions_team(v["tokens"], fx["team1"], aliases)
            m2 = tm.mentions_team(v["tokens"], fx["team2"], aliases)
            strength = 0
            if fx["date"] in v["dates"]:
                r, _ = tm.match_title(v["th"], [fx["date"]], fixtures={fx["date"]: [fx]},
                                      alias_groups=aliases, start_dt=v["start"])
                if r:
                    strength = 4
                elif m1 and m2:
                    strength = 3
            if not strength and (m1 or m2) and diff <= 45:
                strength = 2
            if not strength and not (m1 or m2) and diff <= 15 and \
                    group_history[v["owner"]] & {fx["team1"], fx["team2"]}:
                strength = 1
            if strength:
                cands[i].append((strength, diff, v))

    best_for_video = defaultdict(list)  # видео -> [(сила, матч)]
    for i, lst in cands.items():
        lst.sort(key=lambda x: (-x[0], x[1]))
        best_for_video[lst[0][2]["full_id"]].append((lst[0][0], i))

    written, not_found = 0, []
    for i, fx in enumerate(missing):
        head = f'{fx["date"]} {fx.get("time") or "--:--"} ({fx.get("age") or "?"}) {fx["team1"]} — {fx["team2"]}'
        lst = cands.get(i)
        if not lst:
            not_found.append(fx)
            continue
        s, diff, v = lst[0]
        rivals_same_fx = [x for x in lst[1:] if x[0] == s]
        rivals_same_video = [x for x in best_for_video[v["full_id"]] if x[1] != i and x[0] >= s]
        reliable = (s >= 3 or (s == 2 and diff <= 20)) and not rivals_same_fx and not rivals_same_video
        dt = "" if diff == float("inf") else f", Δ{diff:.0f} мин"
        print(f'{"✅" if reliable else "❓"} {head}')
        print(f'     ← [{METHODS[s]}{dt}] {v["title"][:80]}  https://vk.com/video{v["full_id"]}')
        for s2, d2, v2 in lst[1:3]:
            print(f'     ? [{METHODS[s2]}] {v2["title"][:80]}  https://vk.com/video{v2["full_id"]}')
        if rivals_same_video:
            print("     ! это же видео подходит и к другому матчу — не записываю")
        if reliable and apply:
            if bot.register_official_video(fx, f'https://vk.com/video{v["full_id"]}', v["title"]):
                written += 1
                print("     → ЗАПИСАНО")

    print(f"\nНичего не найдено для {len(not_found)} матчей.")
    clubs = Counter(t for fx in not_found for t in (fx["team1"], fx["team2"]))
    if clubs:
        print("Чаще всего без трансляций (возможно, их группы VK не отслеживаются):")
        for team, n in clubs.most_common(10):
            print(f"   {n:3}  {team}")
    if apply:
        print(f"\nЗаписано ссылок: {written}")
    else:
        print("\nЭто только отчёт. Надёжные находки (✅) записать: python3 audit_missing_videos.py --apply")


if __name__ == "__main__":
    main()
