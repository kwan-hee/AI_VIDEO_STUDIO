#!/usr/bin/env bash
# 플레이리스트 스튜디오 웹 대시보드 (macOS / Linux)
cd "$(dirname "$0")" || exit 1

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
else
  PY="python3"
fi

exec "$PY" -m playlist_studio serve "$@"
