#!/usr/bin/env python3
"""
Облако работает в полную силу только в игровое окно, вне его — раз в час.

  полная работа (циклы каждые 4 мин): за 1 час до первой игры дня — 3 часа после
  начала последней; и 21:50–22:30 (пост на завтра);
  вне окон: один короткий цикл раз в час, остальные запуски — минутная проверка.
Решение принимается в быстрой проверке (только git), до установки пакетов.
ffmpeg (для праздничных роликов) ставится только 15.12–10.01.

Нужен применённый cloud_patch.py.   Запуск (из ~/vk-bot):  python3 cloud_window_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

GH = [
    ("решение о режиме",
     '''    elif meta:
        stale = (time.time() - meta.get("time", 0)) / 60
        work = meta.get("active") == "cloud" or stale >= CLOUD_TAKEOVER_MIN
        log(f"последний снимок {stale:.0f} мин назад ({meta.get('active')}) — {'работаю' if work else 'компьютеры на связи'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"work={'yes' if work else 'no'}\\n")
    return work''',
     '''    mode = "full"
    if meta and not (meta.get("active") == "cloud" and meta.get("request") == "takeback"):
        stale = (time.time() - meta.get("time", 0)) / 60
        full, why_window = _cloud_window()
        mode = "full" if full else "light"
        if meta.get("active") == "cloud":
            # уже работаем: в игровое окно — полностью, вне окна — короткий цикл раз в час
            work = full or stale >= 55
        else:
            work = stale >= CLOUD_TAKEOVER_MIN
        state = "работаю" if work else ("компьютеры на связи" if meta.get("active") != "cloud" else "вне окна, жду часа")
        log(f"последний снимок {stale:.0f} мин назад ({meta.get('active')}); {why_window} — {state}"
            + (f", режим {'полный' if mode == 'full' else 'короткий'}" if work else ""))
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"work={'yes' if work else 'no'}\\nmode={mode}\\n")
    return work


def _cloud_window(now=None):
    """Игровое окно дня по расписанию из снимка: (полная работа?, пояснение)."""
    from datetime import datetime as _dt, timedelta as _td
    now = now or _dt.now()
    if (now.hour, now.minute) >= (21, 50) and (now.hour, now.minute) <= (22, 30):
        return True, "время поста на завтра"
    try:
        fixtures = json.loads((STATE_DIR / "official_fixtures.json").read_text(encoding="utf-8"))
    except Exception:
        return True, "расписания в снимке нет"
    today = now.strftime("%d.%m.%Y")
    times = []
    for f in fixtures:
        if isinstance(f, dict) and f.get("date") == today:
            m = re.match(r"(\\d{1,2}):(\\d{2})", f.get("time") or "")
            if m:
                times.append(now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0))
    if not times:
        return False, "сегодня игр нет"
    start, end = min(times) - _td(hours=1), max(times) + _td(hours=3)
    window = f"окно {start:%H:%M}–{end:%H:%M}"
    return start <= now <= end, window'''),
    ("короткий цикл",
     '''    deadline = time.time() + (0.05 if TEST else CLOUD_WORK_MIN) * 60''',
     '''    light = os.environ.get("CLOUD_MODE") == "light"         # вне игрового окна — один цикл
    deadline = time.time() + (0.05 if TEST or light else CLOUD_WORK_MIN) * 60
    if light:
        log("вне игрового окна — один короткий цикл")'''),
]

WF_OLD_RUN = '''      - name: Работа вместо компьютеров
        if: steps.check.outputs.work == 'yes'
        run: |
          sudo apt-get install -y -qq ffmpeg > /dev/null
          python -m pip install -q requests Pillow imageio imageio-ffmpeg numpy
          python gh_backup.py cloud'''
WF_NEW_RUN = '''      - name: Работа вместо компьютеров
        if: steps.check.outputs.work == 'yes'
        env:
          CLOUD_MODE: ${{ steps.check.outputs.mode }}
        run: |
          md=$(date +%m%d)
          if [ "$md" -ge 1215 ] || [ "$md" -le 0110 ]; then sudo apt-get install -y -qq ffmpeg > /dev/null; fi
          python -m pip install -q requests Pillow imageio imageio-ffmpeg numpy
          python gh_backup.py cloud'''

TEST_ADD = '''

def test_cloud_window():
    """Облако: полная работа — от часа до первой игры до 3 часов после последней и 21:50–22:30."""
    import gh_backup as g
    import json as _json
    from datetime import datetime as _dt
    g.STATE_DIR = HERE / "_state_window"
    g.STATE_DIR.mkdir(exist_ok=True)
    d = "08.11.2026"
    (g.STATE_DIR / "official_fixtures.json").write_text(_json.dumps(
        [{"date": d, "time": "10:00"}, {"date": d, "time": "16:30"}]), encoding="utf-8")
    at = lambda h, m: g._cloud_window(_dt(2026, 11, 8, h, m))[0]
    assert not at(8, 30) and at(9, 5) and at(19, 25) and not at(19, 40) and at(22, 0)
    assert not g._cloud_window(_dt(2026, 11, 9, 12, 0))[0]          # в другой день игр нет
'''


def main():
    gh = BASE / "gh_backup.py"
    c = gh.read_text(encoding="utf-8")
    if "def cloud_check" not in c:
        sys.exit("Сначала примените cloud_patch.py — ничего не изменено")
    if "def _cloud_window" in c:
        print("gh_backup.py: уже исправлено")
    else:
        missing = [n for n, o, _ in GH if c.count(o) != 1]
        if missing:
            sys.exit(f"gh_backup.py: НЕ найдено: {', '.join(missing)} — ничего не изменено")
        shutil.copy(gh, gh.with_name("gh_backup.py.bak_window"))
        for _, o, n in GH:
            c = c.replace(o, n, 1)
        gh.write_text(c, encoding="utf-8")
        print("gh_backup.py: полная работа облака только в игровое окно, вне его — раз в час")
    wf = BASE / ".github" / "workflows" / "cloud-backup.yml"
    w = wf.read_text(encoding="utf-8")
    if "CLOUD_MODE" not in w:
        if WF_OLD_RUN not in w:
            sys.exit("cloud-backup.yml: шаг работы не найден — сценарий не изменён")
        wf.write_text(w.replace(WF_OLD_RUN, WF_NEW_RUN), encoding="utf-8")
        print("cloud-backup.yml: режим работы передаётся из проверки; ffmpeg только в праздники")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_cloud_window" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест игрового окна облака")


if __name__ == "__main__":
    main()
