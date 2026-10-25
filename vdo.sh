#!/usr/bin/env bash
# vdo engine launcher (macOS / Linux)
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"; [ -x "$PY" ] || PY=python3
PYTHONPATH="$HERE:$PYTHONPATH" exec "$PY" -m vdo "$@"
