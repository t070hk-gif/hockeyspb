#!/usr/bin/env python3
"""
Резервный компьютер через GitHub (приватный репозиторий).

  ветка code  — код бота: основной (MacBook) сохраняет и отправляет изменения сам,
                резервный забирает;
  ветка state — последний снимок состояния (посты, индекс видео, кэши) + секреты
                в зашифрованном виде; время снимка — «сердцебиение» основного.

Основной пропал дольше TAKEOVER минут — резервный включается. Основной вернулся —
просит работу, резервный останавливается и отдаёт финальный снимок, основной
забирает данные и продолжает. Двойных постов нет.

    python3 gh_backup.py setup-primary [git@github.com:ВЛАДЕЛЕЦ/РЕПО.git]   — на MacBook
    python3 gh_backup.py setup-standby                                     — на резервном
    python3 gh_backup.py sync                                              — по cron, каждую минуту
    python3 gh_backup.py status                                            — кто сейчас работает
"""
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

BOT = Path(__file__).resolve().parent
HOME = Path(os.environ.get("HOME", str(Path.home())))
STATE_DIR = HOME / ".vkbot-state"
KEY = HOME / ".vkbot_key"
CFG = BOT / "backup" / "gh_config.json"
ROLE = BOT / "backup" / "role"
SECRETS = ["config.json", "vk_tokens.json"]
DEFAULT_REPO = "git@github.com:t070hk-gif/hockeyspb.git"
PY = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
TEST = os.environ.get("GH_BACKUP_TEST") == "1"          # проверка без cron/launchd/pip
TAKEBACK_WAIT = int(os.environ.get("GH_TAKEBACK_WAIT", "300"))


# ----------------------------------------------------------------- помощники
def git(*args, cwd=BOT, check=True):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def cfg():
    return json.loads(CFG.read_text(encoding="utf-8"))


def role():
    return ROLE.read_text().strip() if ROLE.exists() else ""


def log(msg):
    print(f"{time.strftime('%d.%m %H:%M:%S')} {msg}", flush=True)


def notify(text):
    if TEST:
        log(f"[личка] {text}")
        return
    try:
        import requests
        c = json.loads((BOT / "config.json").read_text(encoding="utf-8"))
        requests.post(f"https://api.telegram.org/bot{c['tg_bot_token']}/sendMessage",
                      data={"chat_id": c["admin_id"], "text": text}, timeout=20)
    except Exception as e:
        log(f"уведомление не отправлено: {e}")


def openssl(args, data):
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", *args, "-pass", f"file:{KEY}"],
                       input=data, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="ignore"))
    return r.stdout


def state_files():
    """Файлы состояния: *.json в папке бота, кроме кода (под git) и секретов."""
    tracked = set(git("ls-files").splitlines())
    return [p for p in sorted(BOT.glob("*.json")) if p.name not in tracked and p.name not in SECRETS]


# ----------------------------------------------------------------- ветка state
def _repo():
    """Адрес репозитория: в облаке — из переменной окружения (с токеном GitHub)."""
    return os.environ.get("GH_BACKUP_REPO") or cfg()["repo"]


def ensure_state_repo():
    if (STATE_DIR / ".git").exists():
        return
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    git("init", "-q", cwd=STATE_DIR)
    git("remote", "add", "origin", _repo(), cwd=STATE_DIR)
    git("config", "user.name", "vk-bot", cwd=STATE_DIR)
    git("config", "user.email", "vk-bot@localhost", cwd=STATE_DIR)


def fetch_meta():
    """Последний снимок с GitHub в STATE_DIR; возвращает его meta.json ({} — снимков ещё нет)."""
    ensure_state_repo()
    if subprocess.run(["git", "fetch", "-q", "origin", "state"], cwd=STATE_DIR, capture_output=True).returncode != 0:
        return {}
    git("checkout", "-q", "-B", "state", "origin/state", cwd=STATE_DIR)
    git("reset", "-q", "--hard", "origin/state", cwd=STATE_DIR)
    try:
        return json.loads((STATE_DIR / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def push_snapshot(meta, take_local=True):
    """Отправить снимок: take_local — взять состояние из папки бота; иначе — то, что лежит в STATE_DIR."""
    ensure_state_repo()
    if take_local:
        for p in STATE_DIR.iterdir():
            if p.name != ".git":
                shutil.rmtree(p) if p.is_dir() else p.unlink()
        for p in state_files():
            shutil.copy2(p, STATE_DIR / p.name)
        import tarfile, io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            for name in SECRETS:
                if (BOT / name).exists():
                    tar.add(BOT / name, arcname=name)
        (STATE_DIR / "secrets.enc").write_bytes(openssl([], buf.getvalue()))
    meta = dict(meta, time=int(time.time()), host=socket.gethostname())
    (STATE_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    git("checkout", "-q", "--orphan", "snap", cwd=STATE_DIR)       # один коммит без истории
    git("add", "-A", cwd=STATE_DIR)
    git("commit", "-qm", f"снимок {meta.get('active')} {time.strftime('%d.%m %H:%M')}", cwd=STATE_DIR)
    git("branch", "-D", "state", cwd=STATE_DIR, check=False)
    git("branch", "-m", "state", cwd=STATE_DIR)
    git("push", "-qf", "origin", "state", cwd=STATE_DIR)


def restore():
    """Забрать состояние и секреты из последнего снимка в папку бота."""
    import tarfile, io
    n = 0
    for p in STATE_DIR.glob("*.json"):
        if p.name != "meta.json":
            shutil.copy2(p, BOT / p.name)
            n += 1
    enc = STATE_DIR / "secrets.enc"
    if enc.exists():
        with tarfile.open(fileobj=io.BytesIO(openssl(["-d"], enc.read_bytes())), mode="r") as tar:
            for m in tar.getmembers():
                if m.name in SECRETS:
                    (BOT / m.name).write_bytes(tar.extractfile(m).read())
                    os.chmod(BOT / m.name, 0o600)
    return n


def bots_running():
    r = subprocess.run(["pgrep", "-f", "post_schedule.py|post_standings.py|live_watcher.py|year_stats.py"],
                       capture_output=True)
    return r.returncode == 0


# ----------------------------------------------------------------- синхронизация
def sync_primary():
    meta = fetch_meta()
    if meta.get("active") in ("standby", "cloud"):
        who = "облака" if meta.get("active") == "cloud" else "резервного компьютера"
        n = _takeback(meta)
        log(f"забрал у {who} {n} файлов состояния")
        notify("✅ MacBook снова в работе: данные облака забраны, облако остановлено" if meta.get("active") == "cloud"
               else "✅ MacBook снова в работе: данные с резервного компьютера забраны, резервный остановлен")
    (BOT / ".primary_ok").touch()
    git("add", "-A")                                          # автосохранение кода
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=BOT).returncode != 0:
        git("commit", "-qm", f"Автосохранение {time.strftime('%d.%m.%Y %H:%M')}")
    git("push", "-qf", "origin", "HEAD:code", check=False)
    push_snapshot({"active": "primary"})


def sync_standby():
    active = (BOT / ".standby_active").exists()
    if not active and subprocess.run(["git", "fetch", "-q", "origin", "code"], cwd=BOT, capture_output=True).returncode == 0:
        if git("rev-parse", "HEAD") != git("rev-parse", "FETCH_HEAD"):
            git("reset", "-q", "--hard", "FETCH_HEAD")            # свежий код с MacBook
    meta = fetch_meta()
    if not meta:
        return
    if not active:
        if meta.get("active") == "cloud":                       # работает облако — забираем к себе
            n = _takeback(meta)
            (BOT / ".standby_active").touch()
            push_snapshot({"active": "standby"})
            log(f"забрал работу у облака, состояние {n} файлов")
            notify("🖥 Резервный компьютер забрал работу у облака")
            return
        if meta.get("active") == "standby":                     # были в работе до перезагрузки
            (BOT / ".standby_active").touch()
            return
        stale = (time.time() - meta.get("time", 0)) / 60
        if stale >= cfg().get("takeover_min", 10):
            n = restore()
            (BOT / ".standby_active").touch()
            push_snapshot({"active": "standby"})
            log(f"MacBook не на связи {stale:.0f} мин — включился, состояние {n} файлов")
            notify(f"⚠️ MacBook не на связи {stale:.0f} мин — работу продолжил резервный компьютер")
        return
    if meta.get("request") == "takeback":
        (BOT / ".standby_active").unlink(missing_ok=True)
        for _ in range(24):
            if not bots_running():
                break
            time.sleep(5)
        push_snapshot({"active": "released"})
        log("MacBook вернулся — работу отдал")
    else:
        push_snapshot({"active": "standby"})


def _takeback(meta):
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
    mode = "full"
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
            fh.write(f"work={'yes' if work else 'no'}\nmode={mode}\n")
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
            m = re.match(r"(\d{1,2}):(\d{2})", f.get("time") or "")
            if m:
                times.append(now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0))
    if not times:
        return False, "сегодня игр нет"
    start, end = min(times) - _td(hours=1), max(times) + _td(hours=3)
    window = f"окно {start:%H:%M}–{end:%H:%M}"
    return start <= now <= end, window


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
    light = os.environ.get("CLOUD_MODE") == "light"         # вне игрового окна — один цикл
    deadline = time.time() + (0.05 if TEST or light else CLOUD_WORK_MIN) * 60
    if light:
        log("вне игрового окна — один короткий цикл")
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


def cloud_plan():
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
            fh.write(f"need={'yes' if need else 'no'}\n")
    return need


def sync():
    lock = HOME / ".vkbot-sync.lock"
    try:
        lock.mkdir()
    except FileExistsError:
        if time.time() - lock.stat().st_mtime < 900:
            return
        lock.rmdir()
        lock.mkdir()
    try:
        {"primary": sync_primary, "standby": sync_standby}.get(role(), lambda: None)()
    except Exception as e:
        log(f"ошибка синхронизации: {e}")
    finally:
        lock.rmdir()


# ----------------------------------------------------------------- установка
RUN_SH = """#!/bin/bash
# Запуск бота с учётом роли: основной — пока синхронизация свежая, резервный — только когда включён.
cd "$(dirname "$0")/.." || exit 1
ROLE=$(cat backup/role 2>/dev/null)
if [ "$ROLE" = standby ] && [ ! -f .standby_active ]; then exit 0; fi
if [ "$ROLE" = primary ]; then
  [ -f .primary_ok ] || exit 0
  [ $(( $(date +%s) - $(stat -f %m .primary_ok) )) -lt 300 ] || exit 0
fi
exec "__PY__" "$@"
"""
VK_GUARD_FUNC = '''def _role_allows_run():
    """Резервирование (папка backup/): работать ли боту на этом компьютере сейчас."""
    base = Path(__file__).parent
    role_file = base / "backup" / "role"
    role = role_file.read_text().strip() if role_file.exists() else ""
    if role == "standby":
        return (base / ".standby_active").exists()
    if role == "primary":
        ok = base / ".primary_ok"
        return ok.exists() and time.time() - ok.stat().st_mtime < 300
    return True


'''
VK_LOOP_OLD = '''    while True:
        try:
            access_token, tokens = get_valid_access_token(tokens)
            process_admin_messages(admin_state, access_token)
'''
VK_LOOP_NEW = '''    while True:
        if not _role_allows_run():          # резервирование: сейчас работает другой компьютер
            time.sleep(30)
            continue
        try:
            access_token, tokens = get_valid_access_token(tokens)
            process_admin_messages(admin_state, access_token)
'''
CRON_BOTS = [("*/2 * * * *", "post_schedule.py --live", "schedule_log.txt"),
             ("* * * * *", "live_watcher.py --live", "live_watcher_log.txt"),
             ("*/10 * * * *", "post_standings.py --live", "standings_log.txt"),
             ("*/10 * * * *", "health_check.py", "health_log.txt"),
             ("30 23 * * *", "year_stats.py --monthly", "year_stats_log.txt"),
             ("0 10 * * *", "festive_avatar.py --apply", "festive_log.txt")]


def common_setup(my_role):
    (BOT / "backup").mkdir(exist_ok=True)
    ROLE.write_text(my_role + "\n")
    run = BOT / "backup" / "run.sh"
    run.write_text(RUN_SH.replace("__PY__", PY if not TEST else sys.executable), encoding="utf-8")
    run.chmod(0o755)
    gi = BOT / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    for item in ("backup/role", ".primary_ok", ".standby_active", "config.json", "vk_tokens.json"):
        if item not in lines:
            lines.append(item)
    gi.write_text("\n".join(lines) + "\n", encoding="utf-8")


def install_cron():
    if TEST:
        return
    run, py = BOT / "backup" / "run.sh", PY
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
    keep = [l for l in cur if not re.search(r"vk-bot.*(\.py|sync_to_standby)", l) or "rotate_logs" in l]
    lines = keep + [f"{when} {run} {cmd} >> {BOT}/{logf} 2>&1" for when, cmd, logf in CRON_BOTS]
    lines.append(f"* * * * * {py} {BOT}/gh_backup.py sync >> {BOT}/backup_log.txt 2>&1")
    if not any("rotate_logs" in l for l in lines):
        lines.append(f"10 4 * * * {BOT}/rotate_logs.sh >> {BOT}/rotate_log.txt 2>&1")
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    print("✓ расписание: боты через проверку роли, синхронизация с GitHub каждую минуту")


def patch_vk_bot():
    p = BOT / "vk_to_tg_hockey_bot.py"
    c = p.read_text(encoding="utf-8")
    if "_role_allows_run" in c:
        return
    if c.count(VK_LOOP_OLD) != 1:
        sys.exit("❌ Не нашёл главный цикл VK-бота — установка остановлена")
    i = c.rfind("def main(")
    p.write_text((c[:i] + VK_GUARD_FUNC + c[i:]).replace(VK_LOOP_OLD, VK_LOOP_NEW), encoding="utf-8")
    print("✓ VK-бот уступает работу другому компьютеру, когда нужно")


def setup_primary(repo):
    if subprocess.run(["git", "ls-remote", repo], capture_output=True).returncode != 0:
        sys.exit(f"❌ Нет доступа к {repo}. Добавьте SSH-ключ этого компьютера в GitHub (см. инструкцию) и повторите.")
    print(f"✓ доступ к репозиторию {repo}")
    common_setup("primary")
    CFG.write_text(json.dumps({"repo": repo, "takeover_min": 10}, indent=1), encoding="utf-8")
    if not KEY.exists():
        KEY.write_text(secrets.token_urlsafe(32))
        KEY.chmod(0o600)
    patch_vk_bot()
    if git("remote", check=False).find("origin") < 0:
        git("remote", "add", "origin", repo)
    else:
        git("remote", "set-url", "origin", repo)
    git("add", "-A")
    git("commit", "-qm", "Резервирование через GitHub", check=False)
    git("push", "-qf", "origin", "HEAD:code")
    print("✓ код отправлен в ветку code")
    push_snapshot({"active": "primary"})
    print("✓ первый снимок состояния (секреты зашифрованы) — в ветке state")
    (BOT / ".primary_ok").touch()
    install_cron()
    if not TEST and (BOT / "restart_vkbot.sh").exists():
        subprocess.run([str(BOT / "restart_vkbot.sh")])
    print("\n✅ MacBook готов. Ключ шифрования для резервного компьютера (скопируйте целиком):\n")
    print(f"    {KEY.read_text().strip()}\n")


def setup_standby():
    if not KEY.exists():
        sys.exit(f"❌ Нет ключа {KEY}. Создайте его командой из инструкции и повторите.")
    common_setup("standby")
    if not CFG.exists():
        sys.exit("❌ Нет backup/gh_config.json — папка бота должна быть склонирована из ветки code.")
    if not TEST:
        subprocess.run([PY, "-m", "pip", "install", "-q", "requests", "Pillow", "imageio", "imageio-ffmpeg", "numpy"])
        print("✓ пакеты Python")
    meta = fetch_meta()
    if not meta:
        sys.exit("❌ В ветке state нет снимка — сначала выполните setup-primary на MacBook.")
    n = restore()
    print(f"✓ состояние и секреты с GitHub: {n} файлов + config.json, vk_tokens.json")
    install_cron()
    if TEST:
        return
    plist = HOME / "Library" / "LaunchAgents" / "com.hockeyjunior.vkbot.plist"
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.hockeyjunior.vkbot</string>
  <key>ProgramArguments</key><array><string>{PY}</string><string>-u</string><string>{BOT}/vk_to_tg_hockey_bot.py</string></array>
  <key>WorkingDirectory</key><string>{BOT}</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>{BOT}/vkbot_log.txt</string>
  <key>StandardErrorPath</key><string>{BOT}/vkbot_error.txt</string>
</dict></plist>
""", encoding="utf-8")
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.hockeyjunior.vkbot"], capture_output=True)
    for _ in range(5):
        time.sleep(2)
        if subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist)], capture_output=True).returncode == 0:
            break
    print("✓ VK-бот запущен и ждёт своей очереди")
    print("\n✅ Резервный компьютер готов.")


def status():
    meta = fetch_meta()
    if not meta:
        print("снимков в GitHub ещё нет")
        return
    age = (time.time() - meta.get("time", 0)) / 60
    who = {"primary": "MacBook (основной)", "standby": "резервный компьютер", "released": "передаётся MacBook",
           "cloud": "облако (GitHub)"}
    print(f"Сейчас работает: {who.get(meta.get('active'), meta.get('active'))}; последний снимок {age:.0f} мин назад"
          f" с компьютера {meta.get('host')}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "setup-primary":
        setup_primary(sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REPO)
    elif cmd == "setup-standby":
        setup_standby()
    elif cmd == "sync":
        sync()
    elif cmd == "status":
        status()
    elif cmd == "cloud-check":
        cloud_check()
    elif cmd == "cloud-plan":
        cloud_plan()
    elif cmd == "cloud":
        cloud_work()
    else:
        print(__doc__)
