#!/bin/bash
# Запуск бота с учётом роли: основной — пока синхронизация свежая, резервный — только когда включён.
# Каждый запуск и пропуск с причиной пишется в backup/run_log.txt
cd "$(dirname "$0")/.." || exit 1
LOG=backup/run_log.txt
ROLE=$(cat backup/role 2>/dev/null)
if [ "$ROLE" = standby ] && [ ! -f .standby_active ]; then exit 0; fi
if [ "$ROLE" = primary ]; then
  if [ ! -f .primary_ok ]; then echo "$(date '+%d.%m %H:%M:%S') пропуск $1: нет .primary_ok" >> $LOG; exit 0; fi
  AGE=$(( $(date +%s) - $(stat -f %m .primary_ok) ))
  if [ "$AGE" -ge 300 ]; then echo "$(date '+%d.%m %H:%M:%S') пропуск $1: синхронизация $AGE с назад" >> $LOG; exit 0; fi
fi
echo "$(date '+%d.%m %H:%M:%S') запуск $1" >> $LOG
exec "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" "$@"
