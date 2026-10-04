#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
PY="${PYTHON:-$ROOT/.venv/Scripts/python.exe}"
exec "$PY" "$ROOT/src/agent.py" "$@"
