#!/bin/bash
# Запуск бота с учётом роли: основной — пока синхронизация свежая, резервный — только когда включён.
cd "$(dirname "$0")/.." || exit 1
ROLE=$(cat backup/role 2>/dev/null)
if [ "$ROLE" = standby ] && [ ! -f .standby_active ]; then exit 0; fi
if [ "$ROLE" = primary ]; then
  [ -f .primary_ok ] || exit 0
  [ $(( $(date +%s) - $(stat -f %m .primary_ok) )) -lt 300 ] || exit 0
fi
exec "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" "$@"
