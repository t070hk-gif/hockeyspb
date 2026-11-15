#!/usr/bin/env python3
"""
Таблица источников видео: группы VK, из которых бот собирает трансляции,
и их каналы на YouTube / RUTUBE (из описания и ссылок группы), с отметкой,
подключён ли канал к боту. Пишет sources_table.json и печатает таблицу.
Запуск (из ~/vk-bot):  python3 sources_table.py
"""
import contextlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import requests

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))
with contextlib.redirect_stdout(io.StringIO()):
    import vk_to_tg_hockey_bot as bot

YT_RE = re.compile(r"(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:@[\w.\-]+|channel/UC[\w-]{22}|c/[\w.\-]+|user/[\w.\-]+)|youtu\.be/[\w-]+)", re.I)
RT_RE = re.compile(r"(?:https?://)?(?:www\.)?rutube\.ru/(?:channel/\d+|u/[\w.\-]+|video/[\w]+)/?", re.I)


def norm(s):
    return re.sub(r"[^a-zа-яё0-9]", "", (s or "").lower().replace("ё", "е"))


def load(name):
    try:
        return json.loads((BASE / name).read_text(encoding="utf-8"))
    except Exception:
        return []


def main():
    token, _ = bot.get_valid_access_token(bot.load_tokens())
    ids = list(dict.fromkeys(list(bot.VK_GROUP_IDS) + list(bot.ROSSII_ONLY_GROUP_IDS)))
    groups = []
    for i in range(0, len(ids), 400):
        r = requests.get("https://api.vk.com/method/groups.getById", timeout=30, params={
            "group_ids": ",".join(map(str, ids[i:i + 400])), "fields": "site,description,links,members_count",
            "access_token": token, "v": bot.VK_API_VERSION}).json()
        resp = r.get("response", {})
        groups += resp.get("groups", resp) if isinstance(resp, dict) else resp
    yt_ch, rt_ch = load("youtube_channels.json"), load("rutube_channels.json")

    per_group = Counter()
    try:
        idx = json.loads((BASE / "video_index.json").read_text(encoding="utf-8"))
        seen = set()
        for v in idx.values():
            m = re.search(r"video-(\d+)_(\d+)", (v or {}).get("video_url", "") if isinstance(v, dict) else "")
            if m and m.group(0) not in seen:
                seen.add(m.group(0))
                per_group[int(m.group(1))] += 1
    except Exception:
        pass

    rows = []
    for g in groups:
        text = " ".join([g.get("site") or "", g.get("description") or ""] +
                        [l.get("url", "") for l in g.get("links", []) or []])
        yts = sorted({u.rstrip("/") for u in YT_RE.findall(text)})
        rts = sorted({u.rstrip("/") for u in RT_RE.findall(text)})
        n = norm(g.get("name"))
        yt_on = [c["name"] for c in yt_ch if any(c["channel_id"] in u for u in yts)
                 or (norm(c["name"]) and (norm(c["name"]) in n or n in norm(c["name"])))]
        rt_on = [c["name"] for c in rt_ch if any(f"/channel/{c['id']}" in u for u in rts)
                 or (norm(c["name"]) and (norm(c["name"]) in n or n in norm(c["name"])))]
        rows.append({
            "id": g["id"], "name": g.get("name"), "screen_name": g.get("screen_name"),
            "url": f"https://vk.com/{g.get('screen_name') or 'club' + str(g['id'])}",
            "members": g.get("members_count"), "rossii_only": g["id"] in bot.ROSSII_ONLY_GROUP_IDS,
            "videos": per_group.get(g["id"], 0),
            "youtube": yts, "rutube": rts, "youtube_connected": yt_on, "rutube_connected": rt_on,
        })
    rows.sort(key=lambda r: -r["videos"])
    extra = {"youtube_channels": yt_ch, "rutube_channels": rt_ch}
    (BASE / "sources_table.json").write_text(json.dumps({"groups": rows, **extra}, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    for r in rows:
        print(f"{r['name']} | {r['url']} | видео {r['videos']} | "
              f"YT: {', '.join(r['youtube']) or '-'}{' ✅' + ','.join(r['youtube_connected']) if r['youtube_connected'] else ''} | "
              f"RT: {', '.join(r['rutube']) or '-'}{' ✅' + ','.join(r['rutube_connected']) if r['rutube_connected'] else ''}"
              f"{' | только Кубок России' if r['rossii_only'] else ''}")
    print(f"\nГрупп VK: {len(rows)}; каналов YouTube у бота: {len(yt_ch)}, RUTUBE: {len(rt_ch)}")
    print("Подключённые каналы:", "; ".join([f"YT {c['name']}" for c in yt_ch] + [f"RT {c['name']}" for c in rt_ch]))


if __name__ == "__main__":
    main()
