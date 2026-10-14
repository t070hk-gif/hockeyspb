#!/usr/bin/env python3
"""
spb_protocol.py — разбор протокола матча на странице spb.fhr.ru/games/<id>/.

Каждое событие — блок <div class="match-protocol [match-protocol--вид]">:
слева карточка игрока хозяев, по центру тип события и время, справа — гостей.

summarize(html, team1, team2) -> {
    "goalies":  {1: [("Тараненко", проп.), ...], 2: [...]},   # кто реально стоял в воротах
    "penalty":  (минуты хозяев, минуты гостей) или None,
}

Проверка на конкретном матче:
    python3 spb_protocol.py 26204694
"""
import re
import sys

_BLOCK_SPLIT = re.compile(r'<div class="match-protocol(?=[ "])')
_MODIFIER = re.compile(r'^\s*(match-protocol--[a-z-]+)?')
_TOP = re.compile(r'protocol-time__top">\s*(.*?)\s*</span>', re.S)
_TIME = re.compile(r"(\d{1,3}):(\d{2})")
_NUM = re.compile(r'protocol-player-card__number">\s*(\d+)')
_NAME = re.compile(r'protocol-player-card__name">\s*([^<]+?)\s*<')
_TEAM = re.compile(r'protocol-player-card__name-team">\s*([^<]+?)\s*<')
_LABEL = re.compile(r'protocol-player-card__label[^>]*>(.*?)</(?:span|div)>', re.S)
_SIDEBAR = re.compile(r'protocol-player-card__sidebar[^>]*>(.*?)</div>', re.S)
_PENALTY_MIN = re.compile(r"(\d+)\s*[’'′]")


def _strip(fragment):
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def _card(fragment):
    name = _NAME.search(fragment)
    if not name:
        return None
    num, team = _NUM.search(fragment), _TEAM.search(fragment)
    return {
        "number": num.group(1) if num else "",
        "name": name.group(1).strip(),
        "team": team.group(1).strip() if team else "",
        "label": " ".join(_strip(x) for x in _LABEL.findall(fragment)).strip(),
        "sidebar": " ".join(_strip(x) for x in _SIDEBAR.findall(fragment)).strip(),
        "text": _strip(fragment),
    }


def parse_events(html):
    """Список событий протокола по порядку."""
    html = re.sub(r"<svg.*?</svg>", "", html, flags=re.S)
    events = []
    for chunk in _BLOCK_SPLIT.split(html)[1:]:
        mod = (_MODIFIER.match(chunk).group(1) or "").replace("match-protocol--", "")
        left = chunk.split("match-protocol__left", 1)[-1].split("match-protocol__center", 1)[0]
        center = chunk.split("match-protocol__center", 1)[-1].split("match-protocol__right", 1)[0]
        right = chunk.split("match-protocol__right", 1)[-1] if "match-protocol__right" in chunk else ""
        top = _TOP.search(center)
        t = _TIME.search(_strip(center))
        events.append({
            "kind": mod,
            "label": _strip(top.group(1)) if top else "",
            "minute": int(t.group(1)) + int(t.group(2)) / 60 if t else None,
            "time": f"{t.group(1)}:{t.group(2)}" if t else "",
            "left": _card(left),
            "right": _card(right),
            "center_text": _strip(center),
        })
    return events


def _surname(name):
    return name.split()[0] if name else ""


def summarize(html):
    """Кто стоял в воротах (с пропущенными) и штрафные минуты: стороны 1 (хозяева) и 2 (гости)."""
    events = parse_events(html)
    keepers = [e for e in events if e["kind"] == "keepers" or e["label"].lower().startswith("вратар")]
    # Гол на сайте подписан не словом, а счётом забившей команды ("1", "2", ...)
    goals = [e for e in events if e not in keepers and e["kind"] in ("", "goal")
             and (re.fullmatch(r"\d+", e["label"] or "") or "гол" in e["label"].lower())]
    penalties = [e for e in events if e not in keepers and ("штраф" in e["label"].lower() or "penalt" in e["kind"]
                                                            or _PENALTY_MIN.search(e["center_text"]))]

    result = {"goalies": {1: [], 2: []}, "penalty": None, "teams": {1: "", 2: ""},
              "goals": {1: [], 2: []}}
    for e in keepers:
        if e["left"] and not result["teams"][1]:
            result["teams"][1] = e["left"]["team"]
        if e["right"] and not result["teams"][2]:
            result["teams"][2] = e["right"]["team"]
    for g in goals:
        for side, card in ((1, g["left"]), (2, g["right"])):
            if card and g["minute"] is not None:
                result["goals"][side].append((g["minute"], f"{_surname(card['name'])} {int(g['minute']) + 1}'"))
    for side in (1, 2):
        result["goals"][side] = [s for _, s in sorted(result["goals"][side])]

    # вратари: по каждой стороне — кто когда появлялся в воротах
    timeline = {1: [], 2: []}
    for e in keepers:
        for side, card in ((1, e["left"]), (2, e["right"])):
            if card:
                timeline[side].append((e["minute"] or 0, _surname(card["name"])))
    for side in (1, 2):
        order = []
        for _, who in sorted(timeline[side]):
            if who not in order:
                order.append(who)
        conceded = {who: 0 for who in order}
        opp = 2 if side == 1 else 1
        for g in goals:
            if not (g["right"] if opp == 2 else g["left"]) or g["minute"] is None:
                continue
            in_net = None
            for t, who in sorted(timeline[side]):
                if t <= g["minute"] + 1e-6:
                    in_net = who
            if in_net is None and order:
                in_net = order[0]
            if in_net in conceded:
                conceded[in_net] += 1
        result["goalies"][side] = [(who, conceded[who]) for who in order]

    # штрафное время сторон
    if penalties:
        mins = {1: 0, 2: 0}
        for e in penalties:
            m = _PENALTY_MIN.search(e["center_text"] + " " + " ".join(
                (c["label"] + " " + c["sidebar"]) for c in (e["left"], e["right"]) if c))
            value = int(m.group(1)) if m else 2
            if e["left"]:
                mins[1] += value
            if e["right"]:
                mins[2] += value
        result["penalty"] = (mins[1], mins[2])
    return result


if __name__ == "__main__":
    sys.path.insert(0, ".")
    import spb_fhr_client as client
    game_id = sys.argv[1] if len(sys.argv) > 1 else "26204694"
    page = client.create_session().get(f"https://spb.fhr.ru/games/{game_id}/", timeout=25).text
    for e in parse_events(page):
        side = lambda c: f"{c['number']}.{c['name']} ({c['team']}) [{c['label']}] [{c['sidebar']}]" if c else "—"
        print(f"{e['kind'] or '-':10} | {e['label']:12} | {e['time']:>6} | {side(e['left'])}  ||  {side(e['right'])}")
    print("\nИТОГ:", summarize(page))
