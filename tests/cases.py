"""
Проверки для run_all.py. Каждая функция test_* — отдельный тест; выполняется
во временной копии кода (tests/_tmp), без сети и без настоящего токена.
"""
import contextlib
import io
import json
import py_compile
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(".").resolve()


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


# ------------------------------------------------------------------ общие данные
def _protocol_html():
    def card(num, name, team, label="", sidebar=""):
        return (f'<div class="protocol-player-card"><span class="protocol-player-card__number">{num}</span>'
                f'<a href="/p" class="protocol-player-card__name">{name}</a>'
                f'<span class="protocol-player-card__name-team">{team}</span>'
                + (f'<span class="protocol-player-card__label">{label}</span>' if label else "")
                + (f'<div class="protocol-player-card__sidebar">{sidebar}</div>' if sidebar else "") + "</div>")

    def ev(kind, top, time, left=None, right=None):
        return (f'<div class="match-protocol{" match-protocol--" + kind if kind else ""}">'
                f'<div class="match-protocol__left ">{left or ""}</div><div class="match-protocol__center">'
                f'<span class="protocol-time__top"> {top} </span><div class="protocol-time__bottom">'
                f'<span class="protocol-time__icon"><svg><path d="M1 2"/></svg></span><span> {time} </span></div></div>'
                f'<div class="match-protocol__right ">{right or ""}</div></div>')
    A, B = "СКА-СЕРЕБРЯНЫЕ ЛЬВЫ", "Динамо-юниор"
    return "".join([
        ev("keepers", "Вратарь", "62:38", card(55, "Тараненко Филипп", A), card(70, "Сиваков Александр", B)),
        ev("", "4", "62:38", card(11, "Прокофьев Арсений", A)),
        ev("", "3", "58:30", None, card(24, "Демин Степан", B, "87. Воробьев Александр")),
        ev("penalty", "Штраф", "55:55", card(62, "Горинов Макарий", A, "Грубость", "2’")),
        ev("", "3", "53:29", card(72, "Марц Дмитрий", A, "10. Жилин Родион", "+1")),
        ev("timeout", "Тайм-аут", "53:05", card("", "Тайм-аут", A)),
        ev("penalty", "Штраф", "53:05", None, card(98, "Кравцов Ярослав", B, "Подножка", "2’")),
        ev("", "2", "49:34", card(97, "Гаврилов Григорий", A, "96. Выскубин Арсений, 98. Николаев Максим")),
        ev("penalty", "Штраф", "47:45", None, card(77, "Копытенков Михаил", B, "Блокировка", "2’")),
        ev("penalty", "Штраф", "44:48", None, card(77, "Копытенков Михаил", B, "Задержка клюшкой", "2’")),
        ev("", "1", "43:25", None, card(27, "Полетаев Георгий", B, "18. Карпов Тимур")),
        ev("", "1", "41:28", card(96, "Выскубин Арсений", A, "98. Николаев Максим")),
        ev("penalty", "Штраф", "24:32", None, card(91, "Савостьянов Вячеслав", B, "Грубость", "2’")),
        ev("penalty", "Штраф", "24:32", card(11, "Прокофьев Арсений", A, "Подножка", "2’")),
        ev("", "0", "17:35", None, card(24, "Демин Степан", B, "13. Гершман Михаил")),
        ev("penalty", "Штраф", "08:23", None, card(98, "Кравцов Ярослав", B, "Подножка", "2’")),
        ev("keepers", "Вратарь", "00:00", card(55, "Тараненко Филипп", A), card(70, "Сиваков Александр", B)),
    ])


# ------------------------------------------------------------------ тесты
def test_compile():
    """Все модули собираются без синтаксических ошибок."""
    for f in sorted(HERE.glob("*.py")):
        py_compile.compile(str(f), doraise=True)


def test_config():
    """Настройки читаются из config.json, а не из кода."""
    import config
    assert config.TG_BOT_TOKEN == "TEST:TOKEN" and config.TG_CHAT_ID == -100 and config.ADMIN_ID == 1
    for name in ("post_schedule.py", "post_standings.py", "vk_to_tg_hockey_bot.py", "health_check.py"):
        src = (HERE / name).read_text(encoding="utf-8")
        assert 'TG_BOT_TOKEN = "' not in src, f"токен всё ещё вписан в {name}"


def test_matcher():
    """Регрессионные тесты сопоставления видео с расписанием."""
    out = subprocess.run([sys.executable, "test_team_matcher.py"], capture_output=True, text=True).stdout
    assert "FAIL" not in out and "Итого" in out, out[-600:]


def test_protocol():
    """Протокол spb.fhr.ru: вратари, пропущенные, штрафы, передачи."""
    import spb_protocol as sp
    r = sp.summarize(_protocol_html())
    assert r["goalies"] == {1: [("Тараненко", 3)], 2: [("Сиваков", 4)]}, r["goalies"]
    assert r["penalty"] == (4, 10), r["penalty"]
    assert r["goals"][1][1] == "Гаврилов 50' (Выскубин, Николаев)", r["goals"][1]
    assert r["goals"][2][0] == "Демин 18' (Гершман)", r["goals"][2]


def test_results_banner():
    """Баннер с результатами рисуется: голы, вратари, штраф, несыгранный матч."""
    import results_banner as rb
    rows = [{"time": "14:30", "team1": "СКА Серебряные Львы 11", "team2": "Динамо Юниор 11", "score": "4 : 3ОТ",
             "goals1": ["Выскубин 42' (Николаев)"], "goals2": ["Демин 18'"],
             "goalie1": "Тараненко · 3 проп.", "goalie2": "Сиваков · 4 проп.", "penalty": (4, 10)},
            {"time": "19:00", "team1": "Северсталь 11", "team2": "СКА Стрельна 11", "score": None}]
    rb._logo = lambda name, size: None
    out = HERE / "banner_test.png"
    with quiet():
        rb.render(None, rows, "Вс 04.10.2026", "A", "Первенство СПб 2011 г.р.", out)
    from PIL import Image
    w, h = Image.open(out).size
    assert w == 1280 and 400 < h < 2000, (w, h)


def test_schedule_helpers():
    """post_schedule: названия со spb.fhr.ru, ОТ/ПБ, доверие ручным привязкам."""
    with quiet():
        import post_schedule as ps
    assert ps._spb_display_name("СКА-СЕРЕБРЯНЫЕ ЛЬВЫ", "11") == "СКА Серебряные Львы 11"
    assert ps._spb_display_name("КРАСНАЯ МАШИНА ЮНИОР - 2", "13") == "Красная Машина Юниор 13 2"
    assert ps._spb_display_name("СШ № 1", "13") == "СШ №1 13"
    assert ps._overtime_suffix(["0:1", "0:0", "3:2", "1:0", "0:0"] * 2) == "ОТ"
    assert ps._overtime_suffix(["1:0", "0:1", "1:1", "0:0", "1:0"]) == "ПБ"
    assert ps._overtime_suffix(["2:1", "1:2", "2:1", "0:0", "0:0"]) == ""
    entry = {"video_url": "https://vk.com/video-1_1", "title": "Live: FILMING24SPORT", "manual": True}
    with quiet():
        assert ps._entry_matches_teams(entry, "Северсталь 13", "СКА Стрельна 13")


def test_schedule_fallback():
    """Запасной источник: при недоступном fhspb.ru пост дня строится по spb.fhr.ru,
    а уже опубликованный пост не трогается."""
    with quiet():
        import post_schedule as ps
    def boom(*a, **k):
        raise TimeoutError("fhspb.ru недоступен")
    ps.fetch_schedule_html = boom
    d = datetime.now()
    day = f"{ps._FALLBACK_DAYS[d.weekday()]} {d:%d.%m.%Y}"
    ps._spb_fallback_matches = lambda *a: [
        {"date": day, "time": "14:00", "arena": "", "tournament_id": "6577", "match_id": "spb1",
         "team1": "Северсталь 13", "team2": "СКА Стрельна 13", "score": None,
         "protocol_url": "https://spb.fhr.ru/games/1/"}]
    for state, expect_new in (({}, True), ({f"6577_{day}": {"message_id": 1, "caption": "x"}}, False)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ps.process_tournament("2013", "A", "ПЕРВЕНСТВО", 6577, state, {}, True, official_keys=set())
        out = buf.getvalue()
        assert "spb.fhr.ru" in out and ("НОВЫЙ ПОСТ" in out) == expect_new, out[-400:]


def test_standings_album():
    """Таблица с группами — альбом; обновление правит картинки на месте."""
    with quiet():
        import post_standings as st
    st.IMAGES_DIR.mkdir(exist_ok=True)
    log, counter = [], [4000]

    def ids(k):
        counter[0] += k
        return list(range(counter[0] - k + 1, counter[0] + 1))
    st.send_album = lambda topic, paths, cap="": (log.append("альбом"), ids(len(paths)))[1]
    st.send_photo = lambda topic, path, caption="": (log.append("фото"), ids(1)[0])[1]
    st.edit_photo = lambda mid, path, caption="": log.append("правка")
    st.pin_message = lambda mid: log.append("закреп")
    st._retire_old_table = lambda mid: log.append("убрать")
    st.save_state = lambda s: None
    st.time.sleep = lambda s: None
    st._remember_logos = lambda b: None
    st.draw_standings_image = lambda title, groups, path: Path(path).write_bytes(b"img")
    row = lambda t, p: {"rank": 1, "team": t, "games": 1, "wins": 1, "losses": 0, "losses_ot": 0,
                        "losses_so": 0, "points": p, "logo_url": None}
    data = {"А": [row("СКА", 2)], "Б": [row("Варяги", 2)]}
    st.fetch_standings_by_group = lambda slug, y: data
    st.fhspb_pervenstvo_standings = lambda age, b: b
    run = lambda state: (log.clear(), st._process_tournament_single_post(
        "2011", "ПЕРВЕНСТВО", st.PERVENSTVO_SLUG, "Y", state, False), list(log))[2]
    state = {}
    with quiet():
        assert run(state) == ["альбом", "закреп"]
        assert run(state) == []
        data["А"] = [row("СКА", 4)]
        assert run(state) == ["правка", "правка"]
        assert run({f"{st.PERVENSTVO_SLUG}_Y": {"message_id": 1, "fingerprint": "x"}}) == ["альбом", "закреп", "убрать"]


def test_vk_dialog():
    """Ручная привязка: ошибка в заголовке, исправление команд, время решает возраст."""
    with quiet():
        import vk_to_tg_hockey_bot as bot
    msgs = []
    bot.send_admin_message = lambda t: msgs.append(t)
    fx = {"10.10.2026": [
        {"date": "10.10.2026", "team1": "северсталь", "team2": "ска стрельна", "age": "13",
         "key": "10.10.2026::северсталь|ска стрельна", "time": "14:00"},
        {"date": "10.10.2026", "team1": "динамо", "team2": "ска стрельна", "age": "12",
         "key": "10.10.2026::динамо|ска стрельна", "time": "10:30"},
        {"date": "10.10.2026", "team1": "динамо", "team2": "ска стрельна", "age": "15",
         "key": "10.10.2026::динамо|ска стрельна", "time": "16:30"}]}
    bot._get_fixtures = lambda: fx
    assert "ЖХК Динамо Юниор 16" in bot._apply_group_hints("ЖХК 16 - ЗАНЕВСКИЙ МОЛОТ 16", -114375744)
    assert bot._closest_fixture("10.10.2026", "Севервсталь", "СКА Стрельна", "13")["age"] == "13"

    def dialog(detected, answers):
        msgs.clear()
        st = {"update_offset": 0, "conversation": None}
        bot._try_autodetect_match = lambda o, v, t: detected
        with quiet():
            bot.handle_admin_message("https://vkvideo.ru/video-227371906_456239521", st, "tok")
            for a in answers:
                bot.handle_admin_message(a, st, "tok")
        return msgs[-1]
    last = dialog({"fx": None, "title": "СКА СТРЕЛЬНА 2013 & ДИНАМО 2013", "description": "",
                   "teams": "СКА Стрельна — Динамо", "date": "10.10.2026", "time": "13:50", "age": "13"},
                  ["Северсталь - СКА Стрельна", "+", "+", "+"])
    assert "Привязал к матчу: северсталь — ска стрельна" in last, last
    last = dialog({"fx": None, "title": "Live", "description": "", "teams": None, "date": None,
                   "time": "16:25", "age": None}, ["Динамо - СКА Стрельна", "10.10", "+", "-"])
    assert "2015 г.р." in last, last


def test_health_summary():
    """Вечерняя сводка: матчи, видео, список без видео."""
    import health_check as hc
    d = "10.10.2026"
    fx = [{"date": d, "time": "14:00", "team1": "северсталь", "team2": "ска стрельна", "age": "13",
           "key": f"{d}::северсталь|ска стрельна"},
          {"date": d, "time": "12:00", "team1": "варяги", "team2": "ска звезда", "age": "12",
           "key": f"{d}::варяги|ска звезда"}]
    (HERE / "official_fixtures.json").write_text(json.dumps(fx, ensure_ascii=False), encoding="utf-8")
    (HERE / "video_index.json").write_text(json.dumps(
        {f"{d}::варяги|ска звезда::12": {"video_url": "u", "title": "Варяги - СКА Звезда", "verified": True}},
        ensure_ascii=False), encoding="utf-8")
    text = hc.day_summary(d)
    assert "Матчей: 2, с видео: 1" in text and "северсталь — ска стрельна" in text, text
