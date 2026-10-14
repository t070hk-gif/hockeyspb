#!/usr/bin/env python3
"""
Почему у матча нет видео в посте. Работает без интернета: берёт
расписание дня из official_fixtures.json и ссылки из индекса видео.

    python3 why_no_video.py               — сегодня
    python3 why_no_video.py 09.10.2026    — другой день
"""
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import post_schedule as sched


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%d.%m.%Y")
    fixtures = [f for f in json.loads(Path("official_fixtures.json").read_text(encoding="utf-8"))
                if f["date"] == day]
    if not fixtures:
        print(f"{day}: официальных матчей в расписании нет")
        return
    index = sched.load_video_index()
    ok = 0
    for f in sorted(fixtures, key=lambda x: (x.get("time") or "", x.get("age") or "")):
        base, age = f["key"], f.get("age")
        age_key = f"{base}::{age}" if age else None
        rivals = [g for g in fixtures if g["key"] == base and g.get("age") != age]
        print(f"\n{f.get('time') or '--:--'}  {f['team1']} — {f['team2']}  ({age or '?'} г.р.)")

        entry = index.get(age_key) if age_key else None
        if not entry and base in index and not rivals:
            entry = index[base]
        if not entry:
            if base in index:
                print(f"   ❌ есть только общий ключ без возраста ({index[base]['video_url']}), "
                      f"а эта пара сегодня играет в нескольких возрастах — не показывается")
            else:
                print("   ❌ видео не зарегистрировано")
                near = [k for k in index if k.startswith(day + "::") and (f["team1"] in k or f["team2"] in k)]
                for k in near[:3]:
                    print(f"      похожий ключ: {k} -> {index[k]['video_url']}")
            continue

        kind = "вручную" if entry.get("manual") else "модулем сопоставления" if entry.get("verified") else "старая привязка"
        with redirect_stdout(io.StringIO()):
            passes = sched._entry_matches_teams(entry, f["team1"], f["team2"])
        if passes:
            ok += 1
            print(f"   ✅ в посте будет видео ({kind}): {entry['video_url']}")
        else:
            print(f"   ❌ скрыто самопроверкой ({kind}): заголовок «{entry.get('title', '')[:60]}» "
                  f"не похож на названия команд — {entry['video_url']}")
    print(f"\nИтого: с видео {ok} из {len(fixtures)}")


if __name__ == "__main__":
    main()
