#!/usr/bin/env python3
"""
Ручная привязка видео через бота теперь работает так же надёжно, как
автоматическая:

vk_to_tg_hockey_bot.py
  * ссылка, присланная боту, сначала сопоставляется с официальным
    расписанием (тот же модуль, что и для автоматики: синонимы, подсказки
    групп, время трансляции); если матч найден — видео привязывается сразу,
    без вопросов, и бот пишет, к какому именно матчу;
  * если по видео не понять — бот спрашивает команды/дату/возраст и тоже
    ищет по ним официальный матч, а не собирает ключ «как ввели»;
  * ручная привязка перезаписывает прежнюю ссылку матча (вы явно указали
    видео) и помечается как ручная;
  * привязки модуля сопоставления помечаются как проверенные.

post_schedule.py
  * самопроверка ссылок не отбраковывает ручные и проверенные привязки
    (раньше скрывала, например, «ЖХК 16 - Заневский Молот 16»).

Запуск (из ~/vk-bot):  python3 manual_video_patch.py
Резервные копии: *.bak_manual
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

VK = [
    ("отметка проверенных привязок",
     '    entry = {"video_url": video_url, "title": title}\n',
     '    entry = {"video_url": video_url, "title": title, "verified": True}\n'),
    ("автоопределение по видео",
     '''    return {
        "title": target.get("title", ""),
        "description": target.get("description", ""),
''',
     '''    try:
        fx, _ = _match_video_to_fixture(target.get("title", ""), target.get("date"),
                                        target.get("live_start_time"), owner_id=owner_id)
    except Exception:
        fx = None
    return {
        "fx": fx,
        "title": target.get("title", ""),
        "description": target.get("description", ""),
'''),
    ("сразу привязать найденное",
     '''        admin_state["conversation"] = conv
        return _advance_conversation(admin_state, "")
''',
     '''        if detected is not None and detected.get("fx"):
            send_admin_message(_register_manual(detected["fx"], video_url, detected["title"]))
            admin_state["conversation"] = None
            return True
        admin_state["conversation"] = conv
        return _advance_conversation(admin_state, "")
'''),
    ("регистрация после вопросов",
     '''    age = None if conv["age"] == "-" else conv["age"]
    video_index = load_video_index()
    key = build_match_key(conv["date"], conv["team1"], conv["team2"], age=age)
    video_index[key] = {
        "video_url": conv["video_url"],
        "title": conv.get("title") or f'{conv["team1"]} - {conv["team2"]}',
    }
    save_video_index(video_index)

    age_part = f", возраст {age}" if age else ""
    send_admin_message(f"✅ Зарегистрировано: {conv['team1']} vs {conv['team2']}, {conv['date']}{age_part}")
''',
     '''    age = None if conv["age"] == "-" else conv["age"]
    typed = f'{conv["team1"]} - {conv["team2"]}' + (f" {age}" if age else "")
    try:
        fx, why = team_matcher.match_title(typed, [conv["date"]], fixtures=_get_fixtures(),
                                           alias_groups=team_matcher.load_alias_groups())
    except Exception as e:
        fx, why = None, str(e)
    if fx:
        send_admin_message(_register_manual(fx, conv["video_url"], conv.get("title") or typed))
    else:
        video_index = load_video_index()
        key = build_match_key(conv["date"], conv["team1"], conv["team2"], age=age)
        video_index[key] = {"video_url": conv["video_url"], "title": conv.get("title") or typed, "manual": True}
        save_video_index(video_index)
        send_admin_message(f"⚠️ Официального матча с такими командами {conv['date']} не нашёл ({why}). "
                           f"Записал как есть: {conv['team1']} — {conv['team2']}. "
                           f"Если это матч турнира — проверьте написание команд и дату.")
'''),
]

VK_FUNC_ANCHOR = "def handle_admin_message("
VK_FUNC_ADD = '''def _register_manual(fx, video_url, title):
    """Ручная привязка видео к официальному матчу (перезаписывает прежнюю ссылку)."""
    index = load_video_index()
    entry = {"video_url": video_url, "title": title, "manual": True}
    keys = [fx["key"]] + ([f'{fx["key"]}::{fx["age"]}'] if fx.get("age") else [])
    for k in keys:
        index[k] = entry
    save_video_index(index)
    age = f", 20{fx['age']} г.р." if fx.get("age") else ""
    return (f"✅ Привязал к матчу: {fx['team1']} — {fx['team2']}, {fx['date']}{age}\n"
            f"Ссылка появится в посте в течение пары минут.")


'''

PS = [
    ("самопроверка",
     '''    title = (entry.get("title") or "").upper()
    if not title:
        return True  # нет сохранённого заголовка — сверить не с чем, доверяем как есть
''',
     '''    if entry.get("manual") or entry.get("verified"):
        return True  # привязано вручную или модулем сопоставления — уже проверено
    title = (entry.get("title") or "").upper()
    if not title:
        return True  # нет сохранённого заголовка — сверить не с чем, доверяем как есть
'''),
]


def patch(path, replacements, marker, extra=None):
    content = path.read_text(encoding="utf-8")
    if marker in content:
        print(f"{path.name}: уже применено")
        return True
    missing = [n for n, old, _ in replacements if content.count(old) != 1]
    if extra and content.count(extra[0]) != 1:
        missing.append("место для новой функции")
    if missing:
        print(f"{path.name}: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
        return False
    shutil.copy(path, path.with_name(path.name + ".bak_manual"))
    for _, old, new in replacements:
        content = content.replace(old, new)
    if extra:
        content = content.replace(extra[0], extra[1] + extra[0], 1)
    path.write_text(content, encoding="utf-8")
    print(f"{path.name}: исправлено (резервная копия: {path.name}.bak_manual)")
    return True


def main():
    ok1 = patch(BASE / "vk_to_tg_hockey_bot.py", VK, "def _register_manual(", (VK_FUNC_ANCHOR, VK_FUNC_ADD))
    ok2 = patch(BASE / "post_schedule.py", PS, 'entry.get("manual") or entry.get("verified")')
    sys.exit(0 if ok1 and ok2 else 1)


if __name__ == "__main__":
    main()
