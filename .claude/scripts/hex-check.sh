#!/usr/bin/env bash
# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
# Boundary checker and quality gate for the MCP server (see .claude/skills/mcp-hexagonal).
#   1. httpx is imported only by src/mcp_frankfurter/upstream.py (the outbound adapter owns the wire)
#   2. upstream.py and config.py never import the mcp SDK (the outbound side knows nothing inbound)
#   3. server.py contains no URL literal (tools never build URLs)
#   4. ruff check, ruff format --check, mypy src, pytest with the 100 % line+branch coverage
#      gate (skip the tests with --no-tests)
# Usage: bash .claude/scripts/hex-check.sh [--no-tests]
set -euo pipefail

cd "$(dirname "$0")/../.."

run_tests=1
for arg in "$@"; do
  case "$arg" in
    --no-tests) run_tests=0 ;;
    *) echo "usage: $0 [--no-tests]" >&2; exit 2 ;;
  esac
done

failed=0
SRC="src/mcp_frankfurter"

check() { # <title> <violations>
  echo "== $1"
  if [ -n "$2" ]; then
    printf '%s\n' "$2"
    echo "-- FAIL"
    failed=1
  else
    echo "-- ok"
  fi
}

check "httpx only in upstream.py" \
  "$(grep -rnE '^\s*(import httpx\b|from httpx\b)' "$SRC" --include='*.py' | grep -v "$SRC/upstream.py" || true)"

check "no mcp SDK imports in upstream.py, mappers.py or config.py" \
  "$(grep -nE '^\s*(import mcp\b|from mcp\b)' "$SRC/upstream.py" "$SRC/mappers.py" "$SRC/config.py" || true)"

check "no URL literals in server.py (tools never build URLs)" \
  "$(grep -nE 'https?://' "$SRC/server.py" || true)"

echo "== ruff check"
uv run --frozen ruff check . || failed=1
echo "== ruff format --check"
uv run --frozen ruff format --check . || failed=1
echo "== mypy src"
uv run --frozen mypy src || failed=1
if [ "$run_tests" -eq 1 ]; then
  echo "== pytest + coverage gate"
  uv run --frozen pytest -q --cov --cov-report=term-missing || failed=1
fi

if [ "$failed" -ne 0 ]; then
  echo "hex-check: FAILED"
  exit 1
fi
echo "hex-check: all checks passed"
