#!/usr/bin/env python3
"""
Стиль «Табло»: post_schedule.py передаёт в баннер с результатами признак
идущего матча — если fhspb.ru ещё не дал итог, а spb.fhr.ru уже отдаёт
текущий счёт, счёт на табло горит красным с надписью LIVE (а не выглядит
финальным). Когда матч закончится, картинка перерисуется с итоговым счётом.

Запуск (из ~/vk-bot):  python3 tablo_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent
TARGET = BASE / "post_schedule.py"

ROW_OLD = '''        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score,
                     "goals1": g1, "goals2": g2, **extra})
'''
ROW_NEW = '''        live = bool(score) and not m.get("score") and is_match_live(m["date"], m.get("time") or "")
        rows.append({"time": m.get("time"), "team1": m["team1"], "team2": m["team2"], "score": score,
                     "goals1": g1, "goals2": g2, "live": live or None, **extra})
'''
FP_OLD = '''                            str(r.get("penalty"))) for r in rows), ensure_ascii=False)
'''
FP_NEW = '''                            str(r.get("penalty")), bool(r.get("live"))) for r in rows), ensure_ascii=False)
'''

TEST_ADD = '''

def test_results_banner_live():
    """Табло: идущий матч (красный счёт LIVE) и итог рисуются без ошибок."""
    import results_banner as rb
    rb._logo = lambda name, size: None
    rows = [{"time": "11:00", "team1": "СКА 11", "team2": "Динамо 11", "score": "5 : 0", "penalty": (2, 6)},
            {"time": "14:30", "team1": "СКА Серебряные Львы 11", "team2": "Динамо Юниор 11", "score": "2 : 1",
             "live": True, "goals1": ["Гаврилов 34'"]},
            {"time": "19:00", "team1": "Северсталь 11", "team2": "СКА Стрельна 11", "score": None}]
    out = HERE / "banner_live.png"
    with quiet():
        rb.render(None, rows, "Сб 03.10.2026", "A", "Первенство СПб 2011 г.р.", out)
    from PIL import Image
    assert Image.open(out).size[0] == 1280
'''


def main():
    rb = (BASE / "results_banner.py").read_text(encoding="utf-8")
    if "СТИЛЕ «ТАБЛО»".lower() not in rb.lower() and "Табло" not in rb:
        sys.exit("Сначала положите в папку новый results_banner.py (стиль «Табло») — ничего не изменено")
    content = TARGET.read_text(encoding="utf-8")
    if '"live": live or None' in content:
        print("post_schedule.py: уже исправлено")
    else:
        missing = [n for n, s in (("строка баннера", ROW_OLD), ("отпечаток", FP_OLD)) if content.count(s) != 1]
        if missing:
            sys.exit(f"post_schedule.py: НЕ найдено однозначно: {', '.join(missing)} — файл НЕ изменён")
        shutil.copy(TARGET, TARGET.with_name("post_schedule.py.bak_tablo"))
        TARGET.write_text(content.replace(ROW_OLD, ROW_NEW).replace(FP_OLD, FP_NEW), encoding="utf-8")
        print("post_schedule.py: признак LIVE передаётся в баннер с результатами")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_results_banner_live" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест табло с LIVE")


if __name__ == "__main__":
    main()
