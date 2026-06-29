#!/bin/bash
# 启动看板服务 (端口 8888)
set -euo pipefail

cd "$(dirname "$0")"

PYTHON="${PYTHON:-./venv/bin/python}"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$HOME/.workbuddy/binaries/python/envs/default/bin/python"
fi

PORT="${PORT:-8888}"

nohup "$PYTHON" main.py dashboard --port "$PORT" >> /tmp/dashboard.log 2>&1 &
echo "Dashboard started, PID: $!"
echo "Log: /tmp/dashboard.log"
echo "URL: http://localhost:$PORT"
