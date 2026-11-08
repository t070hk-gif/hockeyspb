#!/usr/bin/env python3
"""
Облегчённая работа облака (GitHub Actions):
  0. ночью (до 7:00) облако не работает, даже если GitHub запустил его с опозданием;
  1. в облаке бот постов обрабатывает только турниры, у которых есть посты на вчера,
     сегодня или завтра (в 21:50–22:30 — все, чтобы вышли посты на завтра);
  2. пауза между циклами считается от начала цикла;
  3. таблицы в облаке — раз в 6 циклов (~24 мин) вместо 3;
  4. пакеты Python кэшируются между запусками (requirements-cloud.txt);
  5. логотипы команд хранятся на диске (logo_cache/, уходит на GitHub с кодом)
     и не скачиваются заново при каждой картинке — и на MacBook тоже.

Нужны применённые cloud_patch.py и cloud_window_patch.py.
Запуск (из ~/vk-bot):  python3 cloud_speed_patch.py
"""
import re
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

GH = [
    ("ночной запрет",
     '''    mode = "full"
    if meta and not (meta.get("active") == "cloud" and meta.get("request") == "takeback"):''',
     '''    mode = "full"
    from datetime import datetime as _dtn
    if _dtn.now().hour < 7 and meta and not (meta.get("active") == "cloud" and meta.get("request") == "takeback"):
        log("ночь (до 7:00) — облако не работает")
        meta = {}
    if meta and not (meta.get("active") == "cloud" and meta.get("request") == "takeback"):'''),
    ("таблицы реже", "    if cycle % 3 == 0:", "    if cycle % 6 == 0:                                   # таблицы — раз в ~24 минуты"),
    ("только активные турниры",
     "                subprocess.run(cmd, cwd=BOT, timeout=600)",
     "                subprocess.run(cmd, cwd=BOT, timeout=600, env=dict(os.environ, CLOUD_FOCUS=\"1\"))"),
    ("пауза от начала цикла",
     '''    while True:
        for cmd in _cloud_commands(cycle):''',
     '''    while True:
        cycle_start = time.time()
        for cmd in _cloud_commands(cycle):'''),
    ("пауза от начала цикла 2",
     "        time.sleep(CLOUD_CYCLE_SEC)",
     "        time.sleep(max(0, CLOUD_CYCLE_SEC - (time.time() - cycle_start)))   # пауза — от начала цикла"),
]

SKIP_FUNC = '''def _cloud_skip(prefix):
    """В облаке (CLOUD_FOCUS=1) — обрабатывать только турниры с постами на вчера/сегодня/завтра.
    В 21:50–22:30 — все турниры, чтобы вышли посты на завтра. prefix — начало ключа поста
    (номер турнира fhspb.ru или ключ турнира junior.fhr.ru)."""
    if os.environ.get("CLOUD_FOCUS") != "1":
        return False
    now = datetime.now()
    if (21, 50) <= (now.hour, now.minute) <= (22, 30):
        return False
    global _CLOUD_ACTIVE
    if _CLOUD_ACTIVE is None:
        days = {(now + timedelta(days=d)).strftime("%d.%m.%Y") for d in (-1, 0, 1)}
        try:
            keys = json.loads(STATE_FILE.read_text(encoding="utf-8")).keys()
        except Exception:
            keys = []
        _CLOUD_ACTIVE = {k.split("_", 1)[0] for k in keys if any(d in k for d in days)}
    return str(prefix) not in _CLOUD_ACTIVE


_CLOUD_ACTIVE = None


'''

LOGO_FUNC = '''def _logo_bytes(url):
    """Картинка логотипа по адресу — с диска (logo_cache/), иначе скачать и сохранить.
    Папка уходит на GitHub с кодом, поэтому и облако не качает логотипы заново."""
    import hashlib
    cache_dir = Path(__file__).parent / "logo_cache"
    path = cache_dir / (hashlib.md5(url.encode()).hexdigest() + ".img")
    if path.exists() and path.stat().st_size > 0:
        return path.read_bytes()
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    cache_dir.mkdir(exist_ok=True)
    path.write_bytes(resp.content)
    return resp.content


'''

TEST_ADD = '''

def test_cloud_focus():
    """Облако: только турниры с постами на вчера/сегодня/завтра; без CLOUD_FOCUS — все."""
    import os as _os
    from datetime import datetime as _dt
    with quiet():
        import post_schedule as ps
    today = _dt.now().strftime("%d.%m.%Y")
    ps.STATE_FILE.write_text(__import__("json").dumps({f"6577_Сб {today}": {}, "6573_Вс 01.01.2026": {}}), encoding="utf-8")
    ps._CLOUD_ACTIVE = None
    _os.environ.pop("CLOUD_FOCUS", None)
    assert not ps._cloud_skip("6573")
    _os.environ["CLOUD_FOCUS"] = "1"
    now = _dt.now()
    if not ((21, 50) <= (now.hour, now.minute) <= (22, 30)):
        assert not ps._cloud_skip("6577") and ps._cloud_skip("6573")
    _os.environ.pop("CLOUD_FOCUS", None)
'''


def patch(path, items, marker, done_msg):
    c = path.read_text(encoding="utf-8")
    if marker in c:
        print(f"{path.name}: уже исправлено")
        return
    missing = [n for n, o, _ in items if c.count(o) != 1]
    if missing:
        sys.exit(f"{path.name}: НЕ найдено: {', '.join(missing)} — ничего не изменено")
    shutil.copy(path, path.with_name(path.name + ".bak_speed"))
    for _, o, n in items:
        c = c.replace(o, n, 1)
    path.write_text(c, encoding="utf-8")
    print(f"{path.name}: {done_msg}")


def main():
    if "def _cloud_window" not in (BASE / "gh_backup.py").read_text(encoding="utf-8"):
        sys.exit("Сначала примените cloud_patch.py и cloud_window_patch.py — ничего не изменено")
    patch(BASE / "gh_backup.py", GH, "ночь (до 7:00)", "ночной запрет, таблицы реже, только активные турниры, пауза от начала цикла")

    ps_path = BASE / "post_schedule.py"
    pc = ps_path.read_text(encoding="utf-8")
    if "def _cloud_skip" in pc:
        print("post_schedule.py: уже исправлено")
    else:
        def after_signature(text, func, insert):
            """Вставить строки сразу после заголовка функции (до первой строки тела), как бы он ни был разбит."""
            start = text.index(f"def {func}(")
            end = text.index(":\n", text.index(")", start)) + 2
            while text[start:end].count("(") != text[start:end].count(")"):
                end = text.index(":\n", end) + 2
            return text[:end] + insert + text[end:]
        if pc.count("def process_tournament(") != 1 or pc.count("def _process_junior(") != 1:
            sys.exit("post_schedule.py: функции турниров не найдены — ничего не изменено")
        shutil.copy(ps_path, ps_path.with_name("post_schedule.py.bak_speed"))
        pc = after_signature(pc, "process_tournament",
                             "    if _cloud_skip(str(tournament_id)):                    # облако: турнир без игр рядом — пропуск\n        return\n")
        pc = after_signature(pc, "_process_junior", "    if _cloud_skip(cfg[\"key\"]):\n        return\n")
        pc = pc.replace("def process_tournament(", SKIP_FUNC + "def process_tournament(", 1)
        ps_path.write_text(pc, encoding="utf-8")
        print("post_schedule.py: в облаке — только турниры с играми рядом")

    st_items = [
        ("помощник", "def _get_logo_image(team_name, logo_url):", LOGO_FUNC + "def _get_logo_image(team_name, logo_url):"),
        ("загрузка",
         '''            resp = requests.get(logo_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            import io
            logo = Image.open(io.BytesIO(resp.content)).convert("RGBA")''',
         '''            import io
            logo = Image.open(io.BytesIO(_logo_bytes(logo_url))).convert("RGBA")   # с диска, если уже скачан'''),
    ]
    patch(BASE / "post_standings.py", st_items, "def _logo_bytes", "логотипы хранятся в logo_cache/")

    rb_items = [("загрузка",
                 '                img = Image.open(io.BytesIO(requests.get(url, timeout=10).content)).convert("RGBA")',
                 '                data = st._logo_bytes(url) if hasattr(st, "_logo_bytes") else requests.get(url, timeout=10).content\n'
                 '                img = Image.open(io.BytesIO(data)).convert("RGBA")')]
    patch(BASE / "results_banner.py", rb_items, "st._logo_bytes", "логотипы из logo_cache/")

    (BASE / "requirements-cloud.txt").write_text("requests\nPillow\nimageio\nimageio-ffmpeg\nnumpy\n", encoding="utf-8")
    wf = BASE / ".github" / "workflows" / "cloud-backup.yml"
    w = wf.read_text(encoding="utf-8")
    if "cache: pip" not in w:
        w = w.replace('          python-version: "3.12"',
                      '          python-version: "3.12"\n          cache: pip\n          cache-dependency-path: requirements-cloud.txt', 1)
        w = w.replace("          python -m pip install -q requests Pillow imageio imageio-ffmpeg numpy",
                      "          python -m pip install -q -r requirements-cloud.txt", 1)
        wf.write_text(w, encoding="utf-8")
        print("cloud-backup.yml: пакеты Python кэшируются между запусками")
    gi = BASE / ".gitignore"
    if gi.exists() and re.search(r"^logo_cache/?$", gi.read_text(encoding="utf-8"), re.M):
        print("⚠️ logo_cache/ указан в .gitignore — уберите строку, чтобы логотипы уходили на GitHub")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_cloud_focus" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест облачного отбора турниров")


if __name__ == "__main__":
    main()
