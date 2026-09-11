#!/usr/bin/env bash
# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
# Stop hook: when src/, tests/ or pyproject.toml have uncommitted changes, remind to run the
# checks. Non-blocking: exits 0 with a systemMessage, never returns decision=block.
set -euo pipefail

cd "${CLAUDE_PROJECT_DIR:-.}"
payload="$(cat || true)"

# Claude Code sets stop_hook_active when Claude is already continuing because of a Stop hook.
case "$payload" in
  *'"stop_hook_active": true'* | *'"stop_hook_active":true'*) exit 0 ;;
esac

changed="$(git status --porcelain -- src tests pyproject.toml 2>/dev/null || true)"
if [ -n "$changed" ]; then
  printf '%s\n' '{"systemMessage": "src/, tests/ or pyproject.toml changed and are uncommitted: run bash .claude/scripts/hex-check.sh (boundaries, ruff, mypy, pytest) before finishing."}'
fi
exit 0
