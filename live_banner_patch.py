#!/usr/bin/env python3
"""
post_schedule.py: live-счёт больше не пишется строкой в тексте поста —
он сразу появляется на баннере (красный счёт с пометкой LIVE), там же голы.
Значок LIVE в тексте: 🔴 → 📡 (красный кружок теперь означает YouTube).
Запуск (из ~/vk-bot):  python3 live_banner_patch.py
"""
import shutil, sys
from pathlib import Path
BASE = Path(__file__).parent
T = BASE / "post_schedule.py"
ITEMS = [
('''                live_marker = " 🔴 LIVE"''', '''                live_marker = " 📡 LIVE"'''),
('''        live_score_line_text = f"Live-счёт: {live_score_line}" if live_score_line else None
''',
 '''        live_score_line_text = None                # live-счёт — на баннере, не в тексте
        if live_score_line:
            _LIVE_SCORES[spb_key] = live_score_line
            if periods_breakdown and spb_match:
                _LIVE_BREAKDOWN[spb_match["game_id"]] = periods_breakdown
'''),
('''_RESULTS_DETAILS_CACHE = {}
''', '''_RESULTS_DETAILS_CACHE = {}
_LIVE_SCORES = {}        # ключ матча -> live-счёт (для баннера)
_LIVE_BREAKDOWN = {}     # game_id -> голы по ходу матча (для баннера)
'''),
('''    breakdown = _RESULTS_DETAILS_CACHE.get(sm["game_id"]) if sm else None''',
 '''    breakdown = (_RESULTS_DETAILS_CACHE.get(sm["game_id"]) or _LIVE_BREAKDOWN.get(sm["game_id"])) if sm else None'''),
('''            score = (sm or {}).get("score")
        g1, g2 = _goals_for_banner(m, spb_lookup)''',
 '''            score = (sm or {}).get("score")
        if not score:                              # идёт матч — live-счёт сразу на баннер
            score = _LIVE_SCORES.get(build_match_key(plain_date(m["date"]), m["team1"], m["team2"]))
        g1, g2 = _goals_for_banner(m, spb_lookup)'''),
]
ITEMS.append((
 '''    global _results_edits_done
    img, img_fp = _results_image(state_key, banner_path, day_matches, spb_lookup, title,''',
 '''    global _results_edits_done
    existing["banner"], existing["title"] = str(banner_path), title   # для live_watcher.py
    img, img_fp = _results_image(state_key, banner_path, day_matches, spb_lookup, title,'''))

LW = Path(BASE / "live_watcher.py")
LW_OLD = '''        existing = state.get(state_key)
        if existing is None or existing.get("caption") == caption:
            continue  # либо поста ещё нет (не наша забота), либо ничего не изменилось

        print(f"[LIVE-ОБНОВЛЕНИЕ] {state_key} — {date_label}")
        if not dry_run:
            try:
                sched.edit_caption(existing["message_id"], caption)
                existing["caption"] = caption'''
LW_NEW = '''        existing = state.get(state_key)
        if existing is None:
            continue  # поста ещё нет — не наша забота
        # live-счёт теперь на баннере: перерисовываем картинку, если счёт/голы изменились
        img, img_fp = None, existing.get("image_fp")
        if existing.get("banner") and Path(existing["banner"]).exists():
            img, img_fp = sched._results_image(state_key, Path(existing["banner"]), day_matches, spb_lookup,
                                               existing.get("title", ""), existing.get("image_fp"))
        image_changed = img is not None and img_fp != existing.get("image_fp")
        if existing.get("caption") == caption and not image_changed:
            continue  # ничего не изменилось

        print(f"[LIVE-ОБНОВЛЕНИЕ{' + баннер' if image_changed else ''}] {state_key} — {date_label}")
        if not dry_run:
            try:
                if image_changed:
                    sched.edit_media(existing["message_id"], img, caption, entry.get("topic_id"))
                    existing["image_fp"] = img_fp
                else:
                    sched.edit_caption(existing["message_id"], caption)
                existing["caption"] = caption'''

c = T.read_text(encoding="utf-8")
if "_LIVE_SCORES" in c:
    print("post_schedule.py: уже исправлено")
else:
    miss = [o.strip()[:60] for o, _ in ITEMS if c.count(o) != 1]
    lw = LW.read_text(encoding="utf-8") if LW.exists() else ""
    if LW.exists() and "live-счёт теперь на баннере" not in lw and lw.count(LW_OLD) != 1:
        miss.append("live_watcher.py: место обновления поста")
    if miss:
        sys.exit(f"НЕ найдено {miss} — файлы НЕ изменены")
    shutil.copy(T, T.with_name("post_schedule.py.bak_livebanner"))
    for o, n in ITEMS:
        c = c.replace(o, n, 1)
    T.write_text(c, encoding="utf-8")
    print("post_schedule.py: live-счёт — на баннере, в тексте 📡 LIVE")
if LW.exists():
    lw = LW.read_text(encoding="utf-8")
    if "live-счёт теперь на баннере" in lw:
        print("live_watcher.py: уже исправлено")
    else:
        shutil.copy(LW, LW.with_name("live_watcher.py.bak_livebanner"))
        if "from pathlib import Path" not in lw:
            lw = "from pathlib import Path\n" + lw
        LW.write_text(lw.replace(LW_OLD, LW_NEW, 1), encoding="utf-8")
        print("live_watcher.py: при голе перерисовывает баннер с live-счётом")
