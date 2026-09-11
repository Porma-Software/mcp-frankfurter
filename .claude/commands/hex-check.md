---
description: Run the boundary checker (httpx only in upstream.py, no URLs in tools, no SDK on the outbound side) plus ruff, ruff format, mypy and pytest with the coverage gate, then summarise
argument-hint: [--no-tests]
allowed-tools: Bash(bash .claude/scripts/hex-check.sh:*), Bash(uv run python scripts/check_scenarios.py:*)
---

Run `bash .claude/scripts/hex-check.sh $ARGUMENTS` from the project root and read the whole
output, then run `uv run python scripts/check_scenarios.py`.

Then report:

1. One line per section (`httpx only in upstream.py`, `no mcp SDK imports in upstream.py or
   config.py`, `no URL literals in server.py`, `ruff check`, `ruff format --check`, `mypy src`,
   `pytest + coverage gate`, `scenario check`) with ok or FAIL.
2. For every failure: the file:line quoted from the output, why it breaks the rule (see
   `.claude/skills/mcp-hexagonal/SKILL.md`) and the smallest fix. For a boundary failure the fix
   is to move the code to the module that owns it, never to relax the check. For a missing
   scenario ID, name the suite (white-box or black-box) it needs a tagged test in.
3. The pytest summary line (passed / failed / deselected) and the coverage total. Coverage
   below 100 % is a missing test, never a reason to lower `fail_under`.
4. Whether `server.py`, `upstream.py` or `mappers.py` changed in this session; if so, remind the
   user to run `make mutation` (Linux/WSL/CI only) before opening the PR.

Do not change files as part of this command: propose the fixes and wait.
