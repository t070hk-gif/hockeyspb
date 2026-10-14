#!/bin/bash
set -e
cd "$(dirname "$0")"
BOT_DIR="$(pwd)"
if ! git --version >/dev/null 2>&1; then
  echo "git не установлен. Запустите: xcode-select --install — и повторите скрипт."
  exit 1
fi
cat > .gitignore << 'EOF'
vk_tokens.json
*token*.json
state.json
posted_days.json
standings_state.json
video_index.json
official_*.json
*_cache.json
admin_*.json
team_logos.json
live_*.json
*.lock
*_log.txt
*.log
*.log.*
logs_archive/
results_images/
standings_images/
banners_v2/
banners_old/
*.tmp
*.bak*
__pycache__/
.DS_Store
EOF
[ -d .git ] || { git init -q; echo "git: репозиторий создан"; }
git config user.name  >/dev/null 2>&1 || git config user.name  "vk-bot"
git config user.email >/dev/null 2>&1 || git config user.email "vk-bot@localhost"
cat > rotate_logs.sh << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"
mkdir -p logs_archive
for f in *_log.txt; do
  [ -f "$f" ] || continue
  size=$(stat -f%z "$f")
  if [ "$size" -gt 10485760 ]; then
    stamp=$(date +%Y%m%d)
    gzip -c "$f" > "logs_archive/${f%.txt}_$stamp.txt.gz" && : > "$f"
    echo "$(date '+%d.%m %H:%M') $f: $((size / 1048576)) МБ -> logs_archive/${f%.txt}_$stamp.txt.gz"
  fi
  ls -1t logs_archive/${f%.txt}_*.gz 2>/dev/null | tail -n +6 | xargs rm -f
done
EOF
chmod +x rotate_logs.sh
git add -A
if git diff --cached --quiet; then echo "git: изменений для снимка нет"
else git commit -q -m "Снимок рабочей версии $(date '+%d.%m.%Y %H:%M')"
     echo "git: снимок сделан, файлов под контролем: $(git ls-files | wc -l | tr -d ' ')"; fi
if crontab -l 2>/dev/null | grep -q "rotate_logs.sh"; then echo "cron: ротация уже настроена"
else (crontab -l 2>/dev/null; echo "10 4 * * * $BOT_DIR/rotate_logs.sh >> $BOT_DIR/rotate_log.txt 2>&1") | crontab -
     echo "cron: ротация логов настроена (каждый день в 04:10)"; fi
echo "Размер логов:"; ls -lh *_log.txt 2>/dev/null | awk '{print "  " $5 "  " $9}'
