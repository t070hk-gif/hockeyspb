#!/usr/bin/env python3
"""
Ручная привязка видео — полный пошаговый диалог.

Если бот сам не нашёл матч по видео, он спрашивает по очереди:
команды, дату, время начала и возраст. К каждому вопросу — подсказка из
видео (заголовок, время начала трансляции): «+» оставляет её, иначе пишется
своё значение; «-» для времени и возраста — не знаю. По собранным данным
ищется официальный матч (время помогает различить одну пару в двух
возрастах); не найден — записывается как есть (например, товарищеская).

Нужны уже применённые manual_video_patch.py (и желательно typo_tolerant_patch.py).
Запуск (из ~/vk-bot):  python3 full_dialog_patch.py
Резервная копия: vk_to_tg_hockey_bot.py.bak_fulldialog
"""
import shutil
import sys
from pathlib import Path

TARGET = Path(__file__).parent / "vk_to_tg_hockey_bot.py"

HANDLE_NEW = '''def handle_admin_message(text: str, admin_state: dict, access_token: str) -> bool:
    """Ручная привязка видео. Возвращает True, если сообщение обработано."""
    conv = admin_state.get("conversation")
    if conv is None:
        m = VK_VIDEO_LINK_RE.search(text)
        if not m:
            return False  # не ссылка на видео и диалог не идёт — игнорируем
        owner_id, video_id = int(m.group(1)), int(m.group(2))
        video_url = f"https://vk.com/video{owner_id}_{video_id}"
        detected = _try_autodetect_match(owner_id, video_id, access_token)
        if detected is not None and detected.get("fx"):
            send_admin_message(_register_manual(detected["fx"], video_url, detected["title"]))
            return True
        prev = {}
        if detected is not None:
            if detected.get("teams"):
                parts = detected["teams"].split(" — ")
                if len(parts) == 2:
                    prev["teams"] = [parts[0], parts[1]]
            for k in ("date", "time", "age"):
                if detected.get(k):
                    prev[k] = detected[k]
        conv = {"step": None, "owner_id": owner_id, "video_id": video_id, "video_url": video_url,
                "title": detected["title"] if detected else None,
                "description": detected["description"] if detected else "",
                "team1": None, "team2": None, "date": None, "time": None, "age": None, "prev": prev}
        intro = "Сам не нашёл этот матч в официальном расписании — уточним по шагам."
        if prev:
            intro += " Где есть подсказка из видео, ответьте «+», чтобы её оставить."
        send_admin_message(intro + " «отмена» — прервать.")
        admin_state["conversation"] = conv
        return _advance_conversation(admin_state, "")
    return _advance_conversation(admin_state, text)
'''

ADVANCE_NEW = '''def _advance_conversation(admin_state: dict, answer_text: str) -> bool:
    """Пошаговый ввод: команды, дата, время, возраст; затем привязка."""
    conv = admin_state["conversation"]
    prev = conv.setdefault("prev", {})
    step = conv.get("step")
    ans = answer_text.strip()
    keep = ans.lower() in ("+", "да", "ок", "ok")

    if step == "awaiting_teams":
        if keep and prev.get("teams"):
            conv["team1"], conv["team2"] = prev["teams"]
        else:
            parts = re.split(r"\\s*[-–—]\\s*|\\s+vs\\.?\\s+", ans, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
                send_admin_message('Не понял. Напишите две команды через дефис: «Команда1 - Команда2»')
                return True
            conv["team1"], conv["team2"] = parts[0].strip(), parts[1].strip()
    elif step == "awaiting_date":
        if keep and prev.get("date"):
            conv["date"] = prev["date"]
        elif re.match(r"^\\d{1,2}\\.\\d{1,2}\\.\\d{4}$", ans):
            d, mth, y = ans.split(".")
            conv["date"] = f"{int(d):02d}.{int(mth):02d}.{y}"
        elif re.match(r"^\\d{1,2}\\.\\d{1,2}$", ans):
            d, mth = ans.split(".")
            conv["date"] = f"{int(d):02d}.{int(mth):02d}.{datetime.now().year}"
        else:
            send_admin_message("Не понял дату. Напишите ДД.ММ.ГГГГ или ДД.ММ:")
            return True
    elif step == "awaiting_time":
        if keep and prev.get("time"):
            conv["time"] = prev["time"]
        elif ans == "-":
            conv["time"] = "-"
        elif re.match(r"^\\d{1,2}[:.]\\d{2}$", ans):
            h, mi = re.split(r"[:.]", ans)
            conv["time"] = f"{int(h):02d}:{mi}"
        else:
            send_admin_message("Не понял время. Напишите ЧЧ:ММ (например 14:00) или «-»:")
            return True
    elif step == "awaiting_age":
        if keep and prev.get("age"):
            conv["age"] = prev["age"]
        else:
            a = re.sub(r"\\D", "", ans) if ans != "-" else "-"
            if re.match(r"^20(09|1[0-8])$", a):
                a = a[2:]
            if a != "-" and not re.match(r"^(09|1[0-8])$", a):
                send_admin_message("Не понял возраст. Напишите год рождения (например 2013 или 13) или «-»:")
                return True
            conv["age"] = a

    def hint(key):
        if not prev.get(key):
            return ""
        value = " — ".join(prev[key]) if key == "teams" else (f"20{prev[key]}" if key == "age" else prev[key])
        return f"\\nПодсказка из видео: {value} — «+», чтобы оставить."

    if not conv.get("team1") or not conv.get("team2"):
        conv["step"] = "awaiting_teams"
        send_admin_message("1/4. Команды через дефис, как в расписании (например: Северсталь - СКА Стрельна)."
                           + hint("teams"))
        return True
    if not conv.get("date"):
        conv["step"] = "awaiting_date"
        send_admin_message("2/4. Дата матча (ДД.ММ.ГГГГ или ДД.ММ)." + hint("date"))
        return True
    if conv.get("time") is None:
        conv["step"] = "awaiting_time"
        send_admin_message("3/4. Время начала матча (например 14:00), или «-», если не знаете." + hint("time"))
        return True
    if conv.get("age") is None:
        conv["step"] = "awaiting_age"
        send_admin_message("4/4. Год рождения (например 2013), или «-», если не важен." + hint("age"))
        return True

    age = None if conv["age"] == "-" else conv["age"]
    typed = f'{conv["team1"]} - {conv["team2"]}' + (f" {age}" if age else "")
    start_dt = None
    if conv["time"] != "-":
        try:
            start_dt = datetime.strptime(f'{conv["date"]} {conv["time"]}', "%d.%m.%Y %H:%M")
        except ValueError:
            start_dt = None
    try:
        fx, why = team_matcher.match_title(typed, [conv["date"]], fixtures=_get_fixtures(),
                                           alias_groups=team_matcher.load_alias_groups(), start_dt=start_dt)
    except Exception as e:
        fx, why = None, str(e)
    if not fx and "_closest_fixture" in globals():
        fx = _closest_fixture(conv["date"], conv["team1"], conv["team2"], age)
    if fx:
        send_admin_message(_register_manual(fx, conv["video_url"], conv.get("title") or typed))
    else:
        video_index = load_video_index()
        key = build_match_key(conv["date"], conv["team1"], conv["team2"], age=age)
        video_index[key] = {"video_url": conv["video_url"], "title": conv.get("title") or typed, "manual": True}
        save_video_index(video_index)
        send_admin_message(f"⚠️ Официального матча «{conv['team1']} — {conv['team2']}», {conv['date']}"
                           f"{f', 20{age} г.р.' if age else ''} в расписании нет ({why}).\\n"
                           f"Записал как есть — если это товарищеская игра, так и нужно. "
                           f"Если матч турнира — пришлите ссылку ещё раз и проверьте данные.")
    admin_state["conversation"] = None
    return True
'''

DETECT_OLD = '''    return {
        "fx": fx,
'''
DETECT_NEW = '''    live = target.get("live_start_time")
    return {
        "fx": fx,
        "time": datetime.fromtimestamp(live).strftime("%H:%M") if live else None,
'''


def replace_function(content, name, new_code):
    """Заменяет функцию верхнего уровня целиком: от «def name(» до первой
    строки без отступа после неё."""
    start = content.index(f"def {name}(")
    pos = content.index("\n", start) + 1
    while pos < len(content):
        line_end = content.find("\n", pos)
        line_end = len(content) if line_end == -1 else line_end
        line = content[pos:line_end]
        if line.strip() and not line[0].isspace():
            break
        pos = line_end + 1
    return content[:start] + new_code.rstrip("\n") + "\n\n\n" + content[pos:]


def main():
    content = TARGET.read_text(encoding="utf-8")
    if '"3/4. Время начала матча' in content:
        print("Уже применено.")
        return
    if "def _register_manual(" not in content or content.count(DETECT_OLD) != 1:
        print("ВНИМАНИЕ: сначала примените manual_video_patch.py — файл НЕ изменён")
        sys.exit(1)
    shutil.copy(TARGET, TARGET.with_name("vk_to_tg_hockey_bot.py.bak_fulldialog"))
    content = content.replace(DETECT_OLD, DETECT_NEW)
    content = replace_function(content, "handle_admin_message", HANDLE_NEW)
    content = replace_function(content, "_advance_conversation", ADVANCE_NEW)
    TARGET.write_text(content, encoding="utf-8")
    print("Готово: пошаговый диалог — команды, дата, время, возраст "
          "(резервная копия: vk_to_tg_hockey_bot.py.bak_fulldialog)")


if __name__ == "__main__":
    main()
