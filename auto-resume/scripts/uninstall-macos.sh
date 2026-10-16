#!/bin/bash
set -euo pipefail

LABEL="com.vibcoding.codex-auto-resume"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
UID_NUM="$(id -u)"

launchctl bootout "gui/${UID_NUM}/${LABEL}" >/dev/null 2>&1 || true
if [[ -f "$PLIST" ]]; then
  launchctl unload "$PLIST" >/dev/null 2>&1 || true
  rm -f "$PLIST"
  echo "已移除 LaunchAgent: $PLIST"
else
  echo "未找到 LaunchAgent: $PLIST"
fi
