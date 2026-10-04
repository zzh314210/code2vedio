#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/Scripts/python.exe}"
if [ "$#" -eq 0 ]; then
  set -- --topic "公务员行测：资料分析中的增长率"
fi
exec "$PY" "$ROOT/src/agent.py" "$@"
