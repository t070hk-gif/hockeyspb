#!/usr/bin/env python3
"""
Исправления по видео 18.10:

team_matcher.py
  * анонс трансляции без даты в заголовке и без времени начала: матч ищется
    в течение недели после загрузки видео (анонсы выкладывают заранее);
  * время из заголовка ("16:00") даёт предпочтение матчу с этим временем;
  * синоним: «Форвард» = «Динамо Форвард».
vk_to_tg_hockey_bot.py
  * проверка удалённых видео: пауза между запросами к VK и повтор при
    ответе «Too many requests per second».
tests/cases.py — тест на оба случая.

Запуск (из ~/vk-bot):  python3 fix_oct18_patch.py
Затем:                  python3 tests/run_all.py  и перезапуск VK-бота
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

TM = [
    ("синоним Форвард",
     '''    ["красная машина юниор 2", "красная машина 2", "кмю 2"],
]''',
     '''    ["красная машина юниор 2", "красная машина 2", "кмю 2"],
    ["динамо форвард", "форвард"],
]'''),
    ("окно дат для анонсов",
     '''def build_date_candidates(title: str, live_start_ts=None, upload_ts=None, window: int = 3) -> list:''',
     '''ANNOUNCE_AHEAD_DAYS = 7      # анонс без даты: матч может быть до недели после загрузки


def build_date_candidates(title: str, live_start_ts=None, upload_ts=None, window: int = 3) -> list:'''),
    ("дни-кандидаты",
     '''    base = datetime.fromtimestamp(base_ts)
    result = [base.strftime("%d.%m.%Y")]
    for k in range(1, window + 1):
        result.append((base + timedelta(days=k)).strftime("%d.%m.%Y"))
        result.append((base - timedelta(days=k)).strftime("%d.%m.%Y"))
    return result''',
     '''    base = datetime.fromtimestamp(base_ts)
    days = [0]
    for k in range(1, window + 1):
        days += [k, -k]
    if not live_start_ts:
        # Только дата загрузки (анонс без даты и без времени начала):
        # клубы выкладывают анонсы за несколько дней — смотрим неделю вперёд.
        days += list(range(window + 1, ANNOUNCE_AHEAD_DAYS + 1))
    return [(base + timedelta(days=d)).strftime("%d.%m.%Y") for d in days]'''),
    ("время из заголовка",
     '''                score = size + (5 if (title_age and fx_age == title_age) else 0) - 0.01 * idx''',
     '''                score = size + (5 if (title_age and fx_age == title_age) else 0) - 0.01 * idx
                if title_time and _hm(fx.get("time")) == title_time:
                    score += 0.5      # время из заголовка совпало с временем матча'''),
    ("разбор времени",
     '''    def collect(allow_squad_omit):''',
     '''    title_time = _hm(_TITLE_TIME_RE.search(title or "").group(0)) if _TITLE_TIME_RE.search(title or "") else None

    def collect(allow_squad_omit):'''),
    ("помощники времени",
     '''def _minutes_from(fx: dict, start_dt) -> float:''',
     '''_TITLE_TIME_RE = re.compile(r"(?<!\\d)([01]?\\d|2[0-3]):([0-5]\\d)(?!\\d)")


def _hm(text):
    """'9:00' / '09:00' -> (9, 0); None, если времени нет."""
    m = re.match(r"\\s*(\\d{1,2}):(\\d{2})", text or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def _minutes_from(fx: dict, start_dt) -> float:'''),
]

VK = [
    ("пауза в проверке удалённых видео",
     '''    videos_param = ",".join(f"{owner_id}_{vid}" for owner_id, vid in video_refs)
    resp = requests.get(
        "https://api.vk.com/method/video.get",
        params={"videos": videos_param, "access_token": access_token, "v": VK_API_VERSION},
        timeout=15,
    )
    data = resp.json()
    if "error" in data:''',
     '''    videos_param = ",".join(f"{owner_id}_{vid}" for owner_id, vid in video_refs)
    for attempt in range(3):
        time.sleep(0.4)                     # VK: не больше 3 запросов в секунду
        resp = requests.get(
            "https://api.vk.com/method/video.get",
            params={"videos": videos_param, "access_token": access_token, "v": VK_API_VERSION},
            timeout=15,
        )
        data = resp.json()
        if data.get("error", {}).get("error_code") == 6:      # Too many requests per second
            time.sleep(1.5 * (attempt + 1))
            continue
        break
    if "error" in data:'''),
]

TEST_ADD = '''

def test_announce_without_date():
    """Анонс без даты, выложенный за 4 дня, и «Форвард» вместо «Динамо Форвард»."""
    import team_matcher as tm
    from datetime import datetime as dt
    fx = {"16.10.2026": [{"date": "16.10.2026", "team1": "гудгол", "team2": "красная машина юниор", "age": "10",
                          "key": "16.10.2026::гудгол|красная машина юниор", "time": "11:00"}],
          "18.10.2026": [{"date": "18.10.2026", "team1": "гудгол", "team2": "красная машина юниор", "age": "10",
                          "key": "18.10.2026::гудгол|красная машина юниор", "time": "16:00"},
                         {"date": "18.10.2026", "team1": "альфа", "team2": "динамо форвард", "age": "11",
                          "key": "18.10.2026::альфа|динамо форвард", "time": "9:00"}]}
    title = "Гудгол 10 - Красная Машина Юниор 10, 16:00,"
    dates = tm.build_date_candidates(title, None, dt(2026, 10, 14, 20, 18).timestamp())
    assert "18.10.2026" in dates, dates
    r, why = tm.match_title(title, dates, fixtures=fx, alias_groups=tm.load_alias_groups())
    assert r and r["date"] == "18.10.2026", (r, why)          # 16:00 в заголовке — матч 18.10, а не 16.10
    r, why = tm.match_title("18.10 09:00 АЛЬФА 11 - ФОРВАРД 11", ["18.10.2026"], fixtures=fx,
                            alias_groups=tm.load_alias_groups())
    assert r and r["team2"] == "динамо форвард", (r, why)
'''


def patch(path, items, marker):
    content = path.read_text(encoding="utf-8")
    if marker in content:
        print(f"{path.name}: уже исправлено")
        return True
    missing = [n for n, old, _ in items if content.count(old) != 1]
    if missing:
        print(f"{path.name}: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
        return False
    shutil.copy(path, path.with_name(path.name + ".bak_oct18"))
    for _, old, new in items:
        content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print(f"{path.name}: исправлено")
    return True


def main():
    ok = patch(BASE / "team_matcher.py", TM, "ANNOUNCE_AHEAD_DAYS")
    ok &= patch(BASE / "vk_to_tg_hockey_bot.py", VK, "не больше 3 запросов в секунду")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_announce_without_date" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест на анонсы без даты")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
