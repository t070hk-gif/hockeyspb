#!/usr/bin/env python3
"""
Наведение порядка в ~/vk-bot перед переездом на VPS.

  1. config.json — токен Telegram, группа, ваш ID (берутся из нынешнего кода);
     в коде вместо них — чтение из config.py. config.json в git не хранится.
  2. Скрипты-патчи и отладочные файлы — в archive/ (ничего не удаляется).
  3. .gitignore: config.json, кэш spb_match_details.json, vkbot_error.txt.
  4. Автотесты — в tests/, запуск: python3 tests/run_all.py
  5. Проверка тестами и снимок в git.

Запуск (из ~/vk-bot):  python3 apply_cleanup.py
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKING = ["post_schedule.py", "post_standings.py", "vk_to_tg_hockey_bot.py", "health_check.py"]

ARCHIVE_EXACT = {
    "generate_banner.py", "weekly_test.py", "results_banner_test.py", "results_banner_test.png",
    "test_groups.py", "check_swallowed_0509.py", "recover_swallowed_videos.py",
    "revalidate_video_index.py", "migrate_video_index.py", "dedupe_standings.py",
    "cleanup_friendly.py", "current_cron.txt", "setup_git_and_logs.sh", "matcher_dry_run.py",
}
ARCHIVE_PATTERNS = ["*_patch.py", "*.html"]

REPLACEMENTS = [
    (r'^TG_BOT_TOKEN = "[^"]+".*$', "from config import TG_BOT_TOKEN  # секреты — в config.json"),
    (r"^TG_CHAT_ID = -?\d+.*$", "from config import TG_CHAT_ID"),
    (r"^TG_CHANNEL_ID = -?\d+.*$", "from config import TG_CHAT_ID as TG_CHANNEL_ID  # группа ВСЕССЫЛКИ.СПБ"),
    (r"^ADMIN_TELEGRAM_USER_ID = \d+.*$", "from config import ADMIN_ID as ADMIN_TELEGRAM_USER_ID"),
    (r"^ADMIN_ID = \d+.*$", "from config import ADMIN_ID"),
]


def git(*args, check=False):
    return subprocess.run(["git", *args], cwd=BASE, capture_output=True, text=True, check=check)


def step_config():
    cfg = BASE / "config.json"
    if cfg.exists():
        print("1. config.json уже есть")
        return
    src = (BASE / "post_schedule.py").read_text(encoding="utf-8")
    token = re.search(r'^TG_BOT_TOKEN = "([^"]+)"', src, re.M)
    chat = re.search(r"^TG_CHAT_ID = (-?\d+)", src, re.M)
    vk = (BASE / "vk_to_tg_hockey_bot.py").read_text(encoding="utf-8")
    admin = re.search(r"^ADMIN_TELEGRAM_USER_ID = (\d+)", vk, re.M)
    if not (token and chat and admin):
        sys.exit("Не нашёл токен/группу/ID в коде — config.json не создан. Заполните его по образцу config.example.json.")
    cfg.write_text(json.dumps({"tg_bot_token": token.group(1), "tg_chat_id": int(chat.group(1)),
                               "admin_id": int(admin.group(1))}, ensure_ascii=False, indent=2), encoding="utf-8")
    cfg.chmod(0o600)
    print("1. config.json создан из нынешних значений в коде")


def step_code():
    changed = []
    for name in WORKING:
        path = BASE / name
        text = path.read_text(encoding="utf-8")
        new = text
        for pattern, repl in REPLACEMENTS:
            new = re.sub(pattern, repl, new, flags=re.M)
        if new != text:
            shutil.copy(path, path.with_name(name + ".bak_cleanup"))
            path.write_text(new, encoding="utf-8")
            changed.append(name)
    leftovers = [n for n in WORKING if re.search(r'^\s*TG_BOT_TOKEN = "', (BASE / n).read_text(encoding="utf-8"), re.M)]
    print(f"2. токены вынесены в config.json: {', '.join(changed) or 'уже было'}"
          + (f"  ВНИМАНИЕ, токен остался в: {leftovers}" if leftovers else ""))


def step_archive():
    (BASE / "archive").mkdir(exist_ok=True)
    targets = {p for p in BASE.iterdir() if p.is_file() and p.name in ARCHIVE_EXACT}
    for pattern in ARCHIVE_PATTERNS:
        targets.update(BASE.glob(pattern))
    targets.discard(BASE / "apply_cleanup.py")
    moved = 0
    for p in sorted(targets):
        dest = BASE / "archive" / p.name
        if git("mv", "-k", p.name, f"archive/{p.name}").returncode != 0 or p.exists():
            shutil.move(str(p), dest)
        moved += 1
    backups = BASE / "archive" / "backups"
    backups.mkdir(exist_ok=True)
    for p in BASE.glob("*.bak*"):
        if p.is_file():
            shutil.move(str(p), backups / p.name)
    tm = BASE / "test_team_matcher.py"
    if tm.exists():
        if git("mv", "test_team_matcher.py", "tests/test_team_matcher.py").returncode != 0 or tm.exists():
            shutil.move(str(tm), BASE / "tests" / "test_team_matcher.py")
    print(f"3. в archive/ убрано файлов: {moved}, резервные копии — в archive/backups/; тест сопоставления — в tests/")


def step_gitignore():
    gi = BASE / ".gitignore"
    lines = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    for item in ("config.json", "spb_match_details.json", "vkbot_error.txt", "health_state.json",
                 "*.bak_cleanup", "tests/_tmp/"):
        if item not in lines:
            lines.append(item)
    gi.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for f in ("spb_match_details.json", "vkbot_error.txt", "config.json"):
        git("rm", "--cached", "-q", f)
    print("4. .gitignore обновлён: config.json, кэши и логи не попадут в git")


def main():
    if not (BASE / "config.py").exists() or not (BASE / "tests" / "run_all.py").exists():
        sys.exit("Распакуйте весь архив cleanup_bundle.tgz в папку бота и запустите снова.")
    step_config()
    step_code()
    step_archive()
    step_gitignore()
    print("5. запускаю автотесты…\n")
    result = subprocess.run([sys.executable, str(BASE / "tests" / "run_all.py")], cwd=BASE)
    if result.returncode != 0:
        print("\nТесты не прошли — снимок в git НЕ сделан. Пришлите вывод.")
        sys.exit(1)
    git("add", "-A")
    commit = git("commit", "-q", "-m", "Порядок: настройки в config.json, архив патчей, автотесты, README")
    print("\ngit: снимок сделан" if commit.returncode == 0 else "\ngit: изменений для снимка нет")


if __name__ == "__main__":
    main()
