#!/usr/bin/env bash
# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
# PostToolUse hook (Edit|Write): sort imports and reformat the Python file Claude just touched.
# Reads the hook payload on stdin. Never blocks: always exits 0, even when ruff is unhappy.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}"

file="$(uv run --frozen --quiet python -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    pass
' 2>/dev/null || true)"

case "$file" in
  *.py)
    if [ -f "$file" ]; then
      uv run --frozen --quiet ruff check --fix --select I --quiet "$file" >/dev/null 2>&1 || true
      uv run --frozen --quiet ruff format --quiet "$file" >/dev/null 2>&1 || true
    fi
    ;;
esac
exit 0
