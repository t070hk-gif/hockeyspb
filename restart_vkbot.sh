#!/bin/bash
# Перезапуск VK-бота: launchd часто не принимает bootstrap сразу после bootout
P=~/Library/LaunchAgents/com.hockeyjunior.vkbot.plist
launchctl bootout gui/$(id -u)/com.hockeyjunior.vkbot 2>/dev/null
for i in 1 2 3 4 5; do
  sleep 2
  launchctl bootstrap gui/$(id -u) "$P" 2>/dev/null && break
done
sleep 2
launchctl list | grep hockeyjunior || echo "VK-бот НЕ запустился — пришлите этот вывод"
