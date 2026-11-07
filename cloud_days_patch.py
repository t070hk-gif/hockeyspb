#!/usr/bin/env python3
"""
Облако работает только в дни с играми.

Утренний сценарий cloud-daily (7:00 МСК, ~1 минута) смотрит расписание из
последнего снимка: есть официальные матчи сегодня или завтра (для поста
в 22:00) — включает дневные проверки cloud-backup (каждые 20 минут);
игр нет — выключает их до следующего утра. Снимок старше 2 дней —
проверки включаются на всякий случай, чтобы облако само обновило расписание.

Нужен применённый cloud_patch.py.   Запуск (из ~/vk-bot):  python3 cloud_days_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

PLAN_FUNC = '''def cloud_plan():
    """Облако, утро: нужны ли сегодня дневные проверки. Пишет need=yes|no для GitHub Actions."""
    from datetime import datetime as _dt, timedelta as _td
    meta = fetch_meta()
    need, why = False, "снимков нет"
    if meta:
        age_days = (time.time() - meta.get("time", 0)) / 86400
        try:
            fixtures = json.loads((STATE_DIR / "official_fixtures.json").read_text(encoding="utf-8"))
        except Exception:
            fixtures = []
        dates = {f.get("date") for f in fixtures if isinstance(f, dict)}
        today = _dt.now()
        days = {today.strftime("%d.%m.%Y"), (today + _td(days=1)).strftime("%d.%m.%Y")}
        games = sorted(d for d in dates if d in days)
        if meta.get("active") == "cloud":
            need, why = True, "облако сейчас в работе"
        elif age_days > 2:
            need, why = True, f"снимок старше 2 дней ({age_days:.0f} дн.) — расписание могло устареть"
        elif games:
            need, why = True, f"есть игры: {', '.join(games)}"
        else:
            why = "игр сегодня и завтра нет"
    log(f"дневные проверки облака: {'ВКЛ' if need else 'выкл'} — {why}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"need={'yes' if need else 'no'}\\n")
    return need


def sync():'''

DAILY = r'''name: cloud-daily
# Каждое утро: есть ли игры сегодня или завтра. Есть — включает дневные проверки облака, нет — выключает.
on:
  schedule:
    - cron: "0 4 * * *"              # 7:00 по Москве
  workflow_dispatch: {}
permissions:
  contents: read
  actions: write
jobs:
  plan:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    env:
      TZ: Europe/Moscow
      GH_BACKUP_REPO: https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }}.git
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: code
          fetch-depth: 1
      - name: Есть ли игры
        id: plan
        run: python3 gh_backup.py cloud-plan
      - name: Включить дневные проверки
        if: steps.plan.outputs.need == 'yes'
        run: gh workflow enable cloud-backup.yml --repo "${{ github.repository }}"
      - name: Выключить дневные проверки до завтра
        if: steps.plan.outputs.need != 'yes'
        run: gh workflow disable cloud-backup.yml --repo "${{ github.repository }}"
'''

TEST_ADD = '''

def test_cloud_plan():
    """Облако: дневные проверки включаются только при играх сегодня/завтра или старом снимке."""
    src = (HERE / "gh_backup.py").read_text(encoding="utf-8")
    assert "def cloud_plan" in src and '"cloud-plan"' in src
    root = next(p for p in (HERE, HERE.parent, HERE.parent.parent) if (p / ".github").exists())
    wf = (root / ".github" / "workflows" / "cloud-daily.yml").read_text(encoding="utf-8")
    assert "gh workflow enable cloud-backup.yml" in wf and "gh workflow disable cloud-backup.yml" in wf
'''


def main():
    gh = BASE / "gh_backup.py"
    c = gh.read_text(encoding="utf-8")
    if "def cloud_check" not in c:
        sys.exit("Сначала примените cloud_patch.py — ничего не изменено")
    if "def cloud_plan" in c:
        print("gh_backup.py: уже исправлено")
    else:
        old_cmd = '''    elif cmd == "cloud-check":
        cloud_check()'''
        new_cmd = '''    elif cmd == "cloud-check":
        cloud_check()
    elif cmd == "cloud-plan":
        cloud_plan()'''
        if c.count("\ndef sync():") != 1 or c.count(old_cmd) != 1:
            sys.exit("gh_backup.py: место не найдено — ничего не изменено")
        shutil.copy(gh, gh.with_name("gh_backup.py.bak_days"))
        c = c.replace("\ndef sync():", "\n" + PLAN_FUNC, 1).replace(old_cmd, new_cmd)
        gh.write_text(c, encoding="utf-8")
        print("gh_backup.py: утренняя проверка расписания для облака")
    wf_dir = BASE / ".github" / "workflows"
    (wf_dir / "cloud-daily.yml").write_text(DAILY, encoding="utf-8")
    backup = wf_dir / "cloud-backup.yml"
    w = backup.read_text(encoding="utf-8")
    w = w.replace('''    - cron: "*/30 5-20 * * *"        # каждые 30 минут, 8:00–23:30 по Москве (время в cron — UTC)''',
                  '''    - cron: "*/20 5-20 * * *"        # каждые 20 минут, 8:00–23:40 по Москве; включается утром, только в дни с играми''')
    backup.write_text(w, encoding="utf-8")
    print("сценарии: cloud-daily (утро, 7:00) и cloud-backup (каждые 20 минут в дни с играми)")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_cloud_plan" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест расписания облака")


if __name__ == "__main__":
    main()
