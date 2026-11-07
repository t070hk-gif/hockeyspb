#!/usr/bin/env python3
"""
Облачный резервный бот на GitHub Actions — третий участник резервирования.

Каждые 30 минут (8:00–23:30 МСК) GitHub запускает короткую проверку снимка
в ветке state. Если MacBook и стационарный Mac молчат дольше 25 минут,
облако забирает состояние, расшифровывает секреты ключом из GitHub Secrets
и ~28 минут работает за них: посты, результаты, LIVE, таблицы, видео.
Вернувшийся MacBook (или резервный Mac) забирает работу обратно.

Запуск (из ~/vk-bot):  python3 cloud_patch.py
"""
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).parent

# ----------------------------------------------------------------- gh_backup.py
GH = [
    ("адрес репозитория",
     '''def ensure_state_repo():
    if (STATE_DIR / ".git").exists():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    git("init", "-q", cwd=STATE_DIR)
    git("remote", "add", "origin", cfg()["repo"], cwd=STATE_DIR)''',
     '''def _repo():
    """Адрес репозитория: в облаке — из переменной окружения (с токеном GitHub)."""
    return os.environ.get("GH_BACKUP_REPO") or cfg()["repo"]


def ensure_state_repo():
    if (STATE_DIR / ".git").exists():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    git("init", "-q", cwd=STATE_DIR)
    git("remote", "add", "origin", _repo(), cwd=STATE_DIR)'''),
    ("основной забирает и у облака",
     '''    meta = fetch_meta()
    if meta.get("active") == "standby":
        log("работает резервный — прошу работу обратно")
        push_snapshot(dict(meta, request="takeback"), take_local=False)
        deadline = time.time() + TAKEBACK_WAIT
        while time.time() < deadline:
            time.sleep(1 if TEST else 15)
            meta = fetch_meta()
            if meta.get("active") == "released":
                break
        n = restore()
        log(f"забрал с резервного {n} файлов состояния")
        notify("✅ MacBook снова в работе: данные с резервного компьютера забраны, резервный остановлен")''',
     '''    meta = fetch_meta()
    if meta.get("active") in ("standby", "cloud"):
        who = "облака" if meta.get("active") == "cloud" else "резервного компьютера"
        n = _takeback(meta)
        log(f"забрал у {who} {n} файлов состояния")
        notify("✅ MacBook снова в работе: данные облака забраны, облако остановлено" if meta.get("active") == "cloud"
               else "✅ MacBook снова в работе: данные с резервного компьютера забраны, резервный остановлен")'''),
    ("резервный забирает у облака",
     '''    if not active:
        if meta.get("active") == "standby":                     # были в работе до перезагрузки''',
     '''    if not active:
        if meta.get("active") == "cloud":                       # работает облако — забираем к себе
            n = _takeback(meta)
            (BOT / ".standby_active").touch()
            push_snapshot({"active": "standby"})
            log(f"забрал работу у облака, состояние {n} файлов")
            notify("🖥 Резервный компьютер забрал работу у облака")
            return
        if meta.get("active") == "standby":                     # были в работе до перезагрузки'''),
    ("рукопожатие и облако",
     '''def sync():''',
     '''def _takeback(meta):
    """Попросить работу у того, кто сейчас работает, дождаться «освободил» (до TAKEBACK_WAIT) и забрать состояние."""
    push_snapshot(dict(meta, request="takeback"), take_local=False)
    deadline = time.time() + TAKEBACK_WAIT
    while time.time() < deadline:
        time.sleep(1 if TEST else 15)
        if fetch_meta().get("active") == "released":
            break
    return restore()


CLOUD_TAKEOVER_MIN = 25        # облако включается, если снимков нет дольше
CLOUD_WORK_MIN = 28            # сколько минут работает один запуск облака
CLOUD_CYCLE_SEC = 240          # пауза между циклами работы


def cloud_check():
    """Облако, быстрая проверка (только git): нужно ли работать. Пишет work=yes|no для GitHub Actions."""
    meta = fetch_meta()
    work = False
    if meta.get("active") == "cloud" and meta.get("request") == "takeback":
        push_snapshot({"active": "released"}, take_local=False)   # компьютер вернулся, облако не работало
        log("компьютер просит работу — отдал")
    elif meta:
        stale = (time.time() - meta.get("time", 0)) / 60
        work = meta.get("active") == "cloud" or stale >= CLOUD_TAKEOVER_MIN
        log(f"последний снимок {stale:.0f} мин назад ({meta.get('active')}) — {'работаю' if work else 'компьютеры на связи'}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as fh:
            fh.write(f"work={'yes' if work else 'no'}\\n")
    return work


def _cloud_commands(cycle):
    py = sys.executable
    cmds = [[py, "post_schedule.py", "--live"], [py, "live_watcher.py", "--live"],
            [py, "vk_to_tg_hockey_bot.py", "--once"]]
    if cycle % 3 == 0:
        cmds.append([py, "post_standings.py", "--live"])
    if TEST:
        cmds = [[py, "-c", "pass"] for _ in cmds]
    return cmds


def cloud_work():
    """Облако, работа: ~CLOUD_WORK_MIN минут циклов, снимок после каждого; при просьбе — отдать работу."""
    meta = fetch_meta()
    first = meta.get("active") != "cloud"
    n = restore()
    log(f"облако в работе, состояние {n} файлов")
    if first:
        notify("☁️ MacBook и резервный компьютер молчат — работу продолжило облако (GitHub)")
        push_snapshot({"active": "cloud"})
    deadline = time.time() + (0.05 if TEST else CLOUD_WORK_MIN) * 60
    cycle = 0
    while True:
        for cmd in _cloud_commands(cycle):
            try:
                subprocess.run(cmd, cwd=BOT, timeout=600)
            except Exception as e:
                log(f"{' '.join(cmd[1:])}: {e}")
        cycle += 1
        now = fetch_meta()
        if now.get("request") == "takeback":
            push_snapshot({"active": "released"})
            log("компьютер вернулся — работу отдал")
            return
        push_snapshot({"active": "cloud"})
        if time.time() + CLOUD_CYCLE_SEC > deadline:
            return
        time.sleep(CLOUD_CYCLE_SEC)


def sync():'''),
    ("команды облака",
     '''    elif cmd == "status":
        status()''',
     '''    elif cmd == "status":
        status()
    elif cmd == "cloud-check":
        cloud_check()
    elif cmd == "cloud":
        cloud_work()'''),
    ("статус",
     '''    who = {"primary": "MacBook (основной)", "standby": "резервный компьютер", "released": "передаётся MacBook"}''',
     '''    who = {"primary": "MacBook (основной)", "standby": "резервный компьютер", "released": "передаётся MacBook",
           "cloud": "облако (GitHub)"}'''),
]

# ----------------------------------------------------------------- vk_to_tg_hockey_bot.py
VK_OLD = '''    ADMIN_CHECK_INTERVAL = 10
    seconds_since_vk_check = POLL_INTERVAL_SECONDS
'''
VK_NEW = '''    ADMIN_CHECK_INTERVAL = 10
    seconds_since_vk_check = POLL_INTERVAL_SECONDS

    if "--once" in sys.argv:                 # облако: один проход и выход
        access_token, tokens = get_valid_access_token(tokens)
        process_admin_messages(admin_state, access_token)
        check_groups_once(state, access_token)
        return
'''

WORKFLOW = r'''name: cloud-backup
# Облачный резервный бот: работает, только если MacBook и резервный Mac молчат дольше 25 минут.
on:
  schedule:
    - cron: "*/30 5-20 * * *"        # каждые 30 минут, 8:00–23:30 по Москве (время в cron — UTC)
  workflow_dispatch: {}
concurrency:
  group: cloud-backup
  cancel-in-progress: false
permissions:
  contents: write
jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 40
    env:
      TZ: Europe/Moscow
      GH_BACKUP_REPO: https://x-access-token:${{ secrets.GITHUB_TOKEN }}@github.com/${{ github.repository }}.git
    steps:
      - uses: actions/checkout@v4
        with:
          ref: code
          fetch-depth: 1
      - name: Нужно ли работать
        id: check
        run: |
          printf '%s' "${{ secrets.VKBOT_KEY }}" > ~/.vkbot_key
          chmod 600 ~/.vkbot_key
          python3 gh_backup.py cloud-check
      - uses: actions/setup-python@v5
        if: steps.check.outputs.work == 'yes'
        with:
          python-version: "3.12"
      - name: Работа вместо компьютеров
        if: steps.check.outputs.work == 'yes'
        run: |
          sudo apt-get install -y -qq ffmpeg > /dev/null
          python -m pip install -q requests Pillow imageio imageio-ffmpeg numpy
          python gh_backup.py cloud
'''

TEST_ADD = '''

def test_cloud_commands():
    """Облако: VK-бот умеет один проход (--once), у резервирования есть режимы облака."""
    src = (HERE / "vk_to_tg_hockey_bot.py").read_text(encoding="utf-8")
    assert '"--once" in sys.argv' in src
    gh = (HERE / "gh_backup.py").read_text(encoding="utf-8")
    assert "def cloud_check" in gh and "def cloud_work" in gh and "def _takeback" in gh
'''


def main():
    gh = BASE / "gh_backup.py"
    c = gh.read_text(encoding="utf-8")
    if "def cloud_check" in c:
        print("gh_backup.py: уже исправлено")
    else:
        missing = [n for n, o, _ in GH if c.count(o) != 1]
        if missing:
            sys.exit(f"gh_backup.py: НЕ найдено однозначно: {', '.join(missing)} — ничего не изменено")
        shutil.copy(gh, gh.with_name("gh_backup.py.bak_cloud"))
        for _, o, n in GH:
            c = c.replace(o, n, 1)
        gh.write_text(c, encoding="utf-8")
        print("gh_backup.py: роль «облако»; MacBook и резервный Mac забирают работу у облака")
    vk = BASE / "vk_to_tg_hockey_bot.py"
    c = vk.read_text(encoding="utf-8")
    if '"--once" in sys.argv' in c:
        print("vk_to_tg_hockey_bot.py: уже исправлено")
    elif c.count(VK_OLD) == 1:
        shutil.copy(vk, vk.with_name("vk_to_tg_hockey_bot.py.bak_cloud"))
        vk.write_text(c.replace(VK_OLD, VK_NEW), encoding="utf-8")
        print("vk_to_tg_hockey_bot.py: режим --once (один проход для облака)")
    else:
        sys.exit("vk_to_tg_hockey_bot.py: место не найдено — VK-бот не изменён")
    wf = BASE / ".github" / "workflows" / "cloud-backup.yml"
    wf.parent.mkdir(parents=True, exist_ok=True)
    wf.write_text(WORKFLOW, encoding="utf-8")
    print("сценарий GitHub Actions: .github/workflows/cloud-backup.yml")
    cases = BASE / "tests" / "cases.py"
    if cases.exists() and "test_cloud_commands" not in cases.read_text(encoding="utf-8"):
        cases.write_text(cases.read_text(encoding="utf-8").rstrip("\n") + "\n" + TEST_ADD, encoding="utf-8")
        print("tests/cases.py: добавлен тест облака")


if __name__ == "__main__":
    main()
