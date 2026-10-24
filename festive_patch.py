#!/usr/bin/env python3
"""
Подключает новогоднюю тему (festive.py):
  post_schedule.py  — пост праздничного дня (15.12–10.01) получает наряженный
                      баннер: гирлянда и снег (и в шапке баннера с результатами);
  post_standings.py — турнирные таблицы в праздники наряжены по сегодняшней дате.
Нужен festive.py рядом.   Запуск (из ~/vk-bot):  python3 festive_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

PS = [
    ("баннер турнира",
     "    banner_path = get_banner_path(age, group, tournament_type)\n",
     "    banner_path = get_banner_path(age, group, tournament_type)\n"
     "    base_banner_path = banner_path\n"),
    ("баннер дня",
     '        state_key = f"{tournament_id}_{date_label}"\n',
     '        state_key = f"{tournament_id}_{date_label}"\n'
     '        try:\n'
     '            import festive\n'
     '            banner_path = festive.season_banner(base_banner_path, date_label)   # праздники — с гирляндой\n'
     '        except Exception:\n'
     '            banner_path = base_banner_path\n'),
]
ST = [
    ("отпечаток таблицы",
     '''                              "local_logos": LOCAL_LOGO_OVERRIDES}, ensure_ascii=False, sort_keys=True)''',
     '''                              "local_logos": LOCAL_LOGO_OVERRIDES, "festive": _festive_now()},
                             ensure_ascii=False, sort_keys=True)'''),
    ("помощник праздника",
     "def draw_standings_image(",
     "def _festive_now():\n"
     "    try:\n"
     "        import festive\n"
     "        return festive.in_season()\n"
     "    except Exception:\n"
     "        return False\n\n\n"
     "def draw_standings_image("),
    ("баннер таблицы",
     "    banner = next((banners / n for n in candidates if (banners / n).exists() and n), None)\n",
     "    banner = next((banners / n for n in candidates if (banners / n).exists() and n), None)\n"
     "    try:\n"
     "        import festive\n"
     "        banner = festive.season_banner(banner)            # в праздники — с гирляндой\n"
     "    except Exception:\n"
     "        pass\n"),
]
TEST_ADD = '''

def test_festive():
    """Новогодняя тема: праздничные даты и наряженный баннер того же размера."""
    import festive
    from datetime import date
    from PIL import Image
    assert festive.in_season(date(2026, 12, 15)) and festive.in_season(date(2027, 1, 10))
    assert not festive.in_season(date(2027, 1, 11)) and not festive.in_season(date(2026, 10, 24))
    src = HERE / "banners" / "2011_groupa_champ.png"
    ny = festive.season_banner(src, "Вс 27.12.2026")
    assert ny != src and Image.open(ny).size == Image.open(src).size
    assert festive.season_banner(src, "Сб 24.10.2026") == src
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
    shutil.copy(path, path.with_name(path.name + ".bak_festive"))
    for _, old, new in items:
        content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print(f"{path.name}: новогодняя тема подключена")
    return True


def main():
    if not (BASE / "festive.py").exists():
        sys.exit("Нет festive.py рядом — ничего не изменено")
    ok = patch(BASE / "post_schedule.py", PS, "festive.season_banner(base_banner_path")
    ok &= patch(BASE / "post_standings.py", ST, "festive.season_banner(banner)")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_festive" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест новогодней темы")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
