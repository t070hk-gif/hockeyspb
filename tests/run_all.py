#!/usr/bin/env python3
"""
Автотесты ботов. Запуск из папки бота:  python3 tests/run_all.py

Тесты работают во временной копии кода (tests/_tmp) с фиктивным токеном и
без обращений к сети — состояние ботов и канал не затрагиваются.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
BASE = TESTS.parent
TMP = TESTS / "_tmp"
COPY_FILES = ["teams.json", "kubok_rossii_teams.json", "fhspb_logo.png"]
COPY_DIRS = ["fonts", "banners", "logos_local"]


def prepare():
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir()
    for f in BASE.glob("*.py"):
        if not f.name.startswith("._"):          # служебные файлы macOS
            shutil.copy(f, TMP / f.name)
    for name in COPY_FILES:
        if (BASE / name).exists():
            shutil.copy(BASE / name, TMP / name)
    for name in COPY_DIRS:
        if (BASE / name).is_dir():
            shutil.copytree(BASE / name, TMP / name)
    for f in ("cases.py", "test_team_matcher.py"):
        if (TESTS / f).exists():
            shutil.copy(TESTS / f, TMP / f)
    (TMP / "config.json").write_text(json.dumps({"tg_bot_token": "TEST:TOKEN", "tg_chat_id": -100, "admin_id": 1}),
                                     encoding="utf-8")


def main():
    prepare()
    src = (TMP / "cases.py").read_text(encoding="utf-8")
    names = re.findall(r"^def (test_\w+)\(", src, re.M)
    docs = dict(re.findall(r'^def (test_\w+)\(\):\n\s+"""(.*?)(?:\n|""")', src, re.M))
    failed = 0
    for name in names:
        r = subprocess.run([sys.executable, "-c", f"import cases; cases.{name}()"],
                           cwd=TMP, capture_output=True, text=True, timeout=180)
        ok = r.returncode == 0
        failed += not ok
        print(f"{'✅' if ok else '❌'} {docs.get(name, name).strip()}")
        if not ok:
            tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
            print("     " + "\n     ".join(tail))
    print(f"\nИтого: {len(names) - failed} из {len(names)} прошло")
    if not failed:
        shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
