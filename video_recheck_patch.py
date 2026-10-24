#!/usr/bin/env python3
"""
vk_to_tg_hockey_bot.py:
  1. Видео, для которого матч не нашёлся, перепроверяется раз в 30 минут
     (пока не старше 10 дней), а не один раз. Анонсы выкладывают раньше, чем
     матч появляется в расписании, — теперь они привяжутся, когда появится.
  2. Трансляция без соперника в заголовке («Live: ХК Легион») — матч ищется
     по клубу группы VK (по истории привязанных видео) и времени начала
     трансляции: матч этого клуба, начинающийся в пределах 30 минут.
     Привязка — только если такой матч один.

Запуск (из ~/vk-bot):  python3 video_recheck_patch.py   затем ~/vk-bot/restart_vkbot.sh
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

ITEMS = [
    ("сопоставление",
     '''    start_dt = datetime.fromtimestamp(live_start) if live_start else None
    return team_matcher.match_title(title, dates, fixtures=_get_fixtures(),
                                    alias_groups=team_matcher.load_alias_groups(),
                                    start_dt=start_dt)
''',
     '''    start_dt = datetime.fromtimestamp(live_start) if live_start else None
    fx, why = team_matcher.match_title(title, dates, fixtures=_get_fixtures(),
                                       alias_groups=team_matcher.load_alias_groups(),
                                       start_dt=start_dt)
    if not fx and live_start and owner_id:
        alt = _match_by_group_team(owner_id, live_start)
        if alt:
            return alt, "по клубу группы и времени трансляции"
    return fx, why


_GROUP_TEAM_CACHE = {}


def _group_team(owner_id):
    """Клуб группы VK — по истории привязанных видео (≥3 видео, клуб в ≥60% из них)."""
    if owner_id in _GROUP_TEAM_CACHE:
        return _GROUP_TEAM_CACHE[owner_id]
    from collections import Counter
    counts, total, seen = Counter(), 0, set()
    for key, v in load_video_index().items():
        url = (v or {}).get("video_url", "") if isinstance(v, dict) else ""
        if f"video{owner_id}_" not in url or url in seen:
            continue
        parts = key.split("::")
        if len(parts) < 2 or "|" not in parts[1]:
            continue
        seen.add(url)
        total += 1
        for t in parts[1].split("|"):
            counts[t] += 1
    team = None
    if total >= 3:
        name, n = counts.most_common(1)[0]
        team = name if n >= 0.6 * total else None
    _GROUP_TEAM_CACHE[owner_id] = team
    return team


def _match_by_group_team(owner_id, live_start):
    """Матч клуба группы, начинающийся в пределах 30 минут от начала трансляции (если он один)."""
    team = _group_team(owner_id)
    if not team:
        return None
    start = datetime.fromtimestamp(live_start)
    found = []
    for f in _get_fixtures().get(start.strftime("%d.%m.%Y"), []):
        if team not in (f.get("team1"), f.get("team2")):
            continue
        hm = re.match(r"(\\d{1,2}):(\\d{2})", f.get("time") or "")
        if hm:
            begin = start.replace(hour=int(hm.group(1)), minute=int(hm.group(2)), second=0)
            if abs((begin - start).total_seconds()) <= 30 * 60:
                found.append(f)
    return found[0] if len(found) == 1 else None
'''),
    ("страховка: список проверенных",
     '''    swept = state.setdefault("_swept_videos", [])
    swept_set = set(swept)''',
     '''    swept = state.setdefault("_swept_videos", {})
    if isinstance(swept, list):                       # прежний формат — «проверено когда-то давно»
        swept = state["_swept_videos"] = {k: 0 for k in swept}'''),
    ("страховка: повторная проверка",
     '''        if vid not in seen_ids or full_id in queue or full_id in swept_set:
            continue''',
     '''        if vid not in seen_ids or full_id in queue:
            continue
        if now - swept.get(full_id, 0) < SWEEP_RETRY_MIN * 60:
            continue                                  # проверяли недавно — ждём'''),
    ("страховка: отметка проверки",
     '''        swept.append(full_id)
        swept_set.add(full_id)
        title = v.get("title", "")''',
     '''        first_try = full_id not in swept
        swept[full_id] = now
        title = v.get("title", "")'''),
    ("страховка: очередь только в первый раз",
     '''        else:
            before = len(queue)
            _queue_unresolved(state, v, title, v.get("description", ""), reason)
            queued += len(queue) - before''',
     '''        elif first_try:                               # в очередь — только при первой проверке
            before = len(queue)
            _queue_unresolved(state, v, title, v.get("description", ""), reason)
            queued += len(queue) - before'''),
    ("страховка: размер списка",
     '''    if len(swept) > 5000:
        del swept[:-5000]''',
     '''    if len(swept) > 5000:
        for k in sorted(swept, key=swept.get)[:-5000]:
            del swept[k]'''),
    ("константа",
     "SWEEP_MAX_AGE_DAYS = 10\n",
     "SWEEP_MAX_AGE_DAYS = 10\nSWEEP_RETRY_MIN = 30          # видео без матча перепроверяется раз в 30 минут\n"),
]


def main():
    content = TARGET.read_text(encoding="utf-8")
    if "SWEEP_RETRY_MIN" in content:
        print("vk_to_tg_hockey_bot.py: уже исправлено")
        return
    missing = [n for n, old, _ in ITEMS if content.count(old) != 1]
    if missing:
        sys.exit(f"vk_to_tg_hockey_bot.py: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
    shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_recheck"))
    for _, old, new in ITEMS:
        content = content.replace(old, new)
    TARGET.write_text(content, encoding="utf-8")
    print("vk_to_tg_hockey_bot.py: видео без матча перепроверяются раз в 30 минут; "
          "трансляции без соперника — по клубу группы и времени")


if __name__ == "__main__":
    main()
