# CLAUDE.md — mcp-frankfurter

MCP server exposing the Frankfurter API (ECB euro reference exchange rates, no key needed) as
tools, built on the official `mcp` SDK (`MCPServer`, 2.x), Python 3.14, packaged with uv, src
layout. Five tools live in `server.py` — `convert`, `latest_rates`, `historical_rate`,
`rate_timeseries`, `list_currencies` — see `docs/DECISIONS.md` for the chosen API version and the
ECB working-day rule, and `docs/scenarios.md` for the FX-*/SRV-*/AUTH-* scenario catalogue both
integration suites are tagged against. This is a **public** repository (MIT): never add anything
that points inside Porma's private infrastructure.

## Commands

```bash
uv sync                          # install (Python 3.14 pinned in .python-version)
uv run pytest -q                 # tests; respx mocks every upstream call, no network
uv run pytest -q --cov --cov-report=term-missing   # = make test: 100 % line+branch gate
uv run python scripts/check_scenarios.py           # = make scenarios: docs/scenarios.md vs both suites
uv run ruff check . && uv run ruff format --check . && uv run mypy src   # = make lint
uv run mcp-frankfurter            # stdio transport
MCP_TRANSPORT=streamable-http MCP_AUTH_TOKEN=... uv run mcp-frankfurter  # HTTP on 127.0.0.1:8000
docker build -t mcp-frankfurter . && docker run --rm -p 8000:8000 -e MCP_AUTH_TOKEN=... mcp-frankfurter
make mutation                    # mutmut on server/upstream/mappers, 0 survivors (Linux/WSL/Docker only)
bash scripts/scan-secrets-local.sh   # = make secrets-scan: gitleaks over full history, Windows-safe
```

`make` is not available on the Windows dev machine: run the commands above directly. CI runs
`make lint`, `make scenarios`, `make test` and, in its own job, `make mutation`. The
`gitleaks-history` CI job (`.github/workflows/secrets.yml`) is reproduced locally with
`scripts/scan-secrets-local.sh` rather than typing the raw `docker run -v ...:/repo` command by
hand: Git Bash on Windows rewrites a bare `/repo` argument into an MSYS install path before
docker ever sees it, and the script sets `MSYS_NO_PATHCONV=1` to stop that.

## Layout

- `src/mcp_frankfurter/config.py` — `Settings` (pydantic-settings, `.env`). HTTP transport refuses to start without `MCP_AUTH_TOKEN`.
- `src/mcp_frankfurter/mappers.py` — the only module that maps an upstream payload to a typed record and a typed record to a tool DTO. Pure functions, no `httpx`/`mcp` import.
- `src/mcp_frankfurter/upstream.py` — the only module that knows the upstream API (URLs, params, retry). Calls `mappers.py` to parse; `UpstreamError` is the only exception it raises.
- `src/mcp_frankfurter/server.py` — `MCPServer` instance and the five tools (`convert`, `latest_rates`, `historical_rate`, `rate_timeseries`, `list_currencies`). Validate input, call upstream, map through `mappers.py`, raise `ToolError` with a clear message.
- `src/mcp_frankfurter/auth.py` — pure-ASGI bearer-token middleware; `GET /healthz` is exempt.
- `src/mcp_frankfurter/__main__.py` — entry point: stdio via `mcp.run()`, HTTP via uvicorn with the middleware and `/healthz` added to the SDK app.
- `docs/DECISIONS.md` — the API version probe (v2, every tool) and the ECB working-day rule.
- `docs/scenarios.md` — the scenario catalogue; `scripts/check_scenarios.py` and `scripts/check_mutants.py` are the gates that keep it and the mutation run honest.
- `tests/unit/` — settings, composition-root wiring; no scenario IDs. `tests/integration/whitebox/` and `tests/integration/blackbox/` — every user-facing behaviour tagged with a `docs/scenarios.md` ID in both. `tests/test_live.py` is the opt-in canary.

## Rules

- Never hit the real network in tests; mock with `respx`. The one live smoke test (`tests/test_live.py`) is marked `live` and deselected by default (`uv run pytest -m live`).
- Tools return data or raise `ToolError`; never let a stack trace reach the client.
- Secrets only via environment (`SecretStr` in `Settings`); never log them.
- Keep the adapter boundary: `httpx` only in `upstream.py`, tools must not build URLs, `upstream.py`/`mappers.py`/`config.py` never import `mcp`. `bash .claude/scripts/hex-check.sh` enforces it.
- Every value crossing the payload/record/DTO boundary goes through `mappers.py`; `server.py` and `upstream.py` never build one of those literals themselves.
- Add a tool: use v2 of the Frankfurter API (see `docs/DECISIONS.md`), carry `rate_date` on every result plus a plain-language note whenever it differs from the requested date, type every argument, write a rich docstring (the model reads it), add a `docs/scenarios.md` row per happy/failure path and a tagged test in **both** integration suites.
- Coverage of `src/mcp_frankfurter` stays at 100 % line and branch (`fail_under = 100`): a new branch needs a test, never a lower threshold. `make mutation` must leave `server.py`/`upstream.py`/`mappers.py` with 0 unexplained survivors.
- Pin the outcome, not the call: `pytest.raises(..., match="substring")` still matches mutmut's mutated `"XX...XX"` literal; assert the full message or the full log line instead.
- MIT-licensed public repo: every source and script header is `# Copyright (c) 2026 Nahúm Cueto López (Porma Software)` then `# SPDX-License-Identifier: MIT`; never anything pointing inside Porma's private infrastructure (no local paths, runner names, private repo or board links).
- Lint and tests green before committing; Conventional Commits.

## Claude Code assets (`.claude/`)

- `settings.json` — allows the `uv`, `git` read and `docker build` commands above; denies `rm -rf`, force pushes and reading `.env`. Hooks: `scripts/format.sh` runs `ruff` (imports + format) after every Edit/Write; `scripts/test-reminder.sh` reminds to run the checks on Stop when `src/` or `tests/` are dirty (non-blocking).
- Skills: `skills/mcp-hexagonal` (layer map, dependency rule, how to add a tool end to end) and `skills/mcp-testing` (the unit/white-box/black-box split, the scenario catalogue, respx patterns, in-memory client, the coverage and mutation gates).
- Agents: `agents/mcp-reviewer` (read-only review: boundary, tool contract, LLM-facing errors, secrets, auth, the scenario and mutation gates; severity output) and `agents/feature-planner` (writes `docs/specs/<date>-<slug>.md` before any code; creates the directory on first use).
- Commands: `/mcp-tool <name>` (scaffold mapper + upstream method + tool + tests in both suites + scenario row + README row, confirms first) and `/hex-check [--no-tests]` (runs `scripts/hex-check.sh` plus the scenario check, and summarises).
