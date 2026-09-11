# mcp-frankfurter

An [MCP](https://modelcontextprotocol.io) server that exposes the [Frankfurter
API](https://frankfurter.dev) — ECB euro reference exchange rates, no API key needed — as tools
for Claude (Desktop, Code or any MCP client). Built on the official `mcp` SDK (`MCPServer`, 2.x),
Python 3.14, packaged with `uv`, src layout.

**Status: scaffold.** This slice wires the composition root, the transport and the test/CI
harness with no Frankfurter tool registered yet — see [`docs/DECISIONS.md`](docs/DECISIONS.md)
for the chosen API version and [`docs/scenarios.md`](docs/scenarios.md) for the scenario
catalogue the tools will grow into.

What you get so far:

- One adapter module (`upstream.py`) that will own every detail of the Frankfurter API once the
  tools land.
- Two transports: **stdio** for desktop clients and **streamable HTTP** for remote use, the
  latter protected by a bearer token and with an open `GET /healthz`.
- Settings from environment / `.env` (pydantic-settings), fail-fast on misconfiguration.
- Tests that never touch the network (`respx`), including a real MCP round trip in memory, at
  **100 % line and branch coverage** of `src/mcp_frankfurter` enforced by `make test`, plus one
  opt-in live smoke test against the real API.
- `Dockerfile` (non-root, health check), `docker-compose.yml`, `Makefile`, GitHub Actions CI
  (lint, scenarios, tests, Docker build, mutation testing, secret scanning).
- Claude Code project assets in `.claude/`: permissions and hooks, two skills, two agents, two
  commands and a boundary checker (see [Claude Code assets](#claude-code-assets)).

## Quick start

```bash
uv sync                 # creates .venv with Python 3.14 (.python-version) and every dependency
uv run pytest -q        # green, no network needed
uv run mcp-frankfurter  # starts on stdio and waits for an MCP client
```

Or `make dev`. To poke at the tools interactively, `uv run mcp dev src/mcp_frankfurter/server.py`
opens the MCP Inspector (needs `npx`).

## Registering the server

### Claude Desktop (stdio)

Edit `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`) and restart Claude Desktop:

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/mcp-frankfurter", "run", "mcp-frankfurter"]
    }
  }
}
```

If Claude Desktop cannot find `uv`, use its absolute path (`which uv` / `where uv`) as `command`.

### Claude Code

One-off, from any directory:

```bash
claude mcp add mcp-frankfurter -- uv --directory /absolute/path/to/mcp-frankfurter run mcp-frankfurter
```

Shared with the team through a `.mcp.json` committed at the project root:

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "command": "uv",
      "args": ["run", "mcp-frankfurter"]
    }
  }
}
```

Against a server already running over HTTP (token from the environment, never in the file):

```bash
claude mcp add --transport http mcp-frankfurter http://127.0.0.1:8000/mcp \
  --header "Authorization: Bearer ${MCP_AUTH_TOKEN}"
```

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp",
      "headers": { "Authorization": "Bearer ${MCP_AUTH_TOKEN}" }
    }
  }
}
```

## Running over HTTP

The HTTP transport refuses to start without `MCP_AUTH_TOKEN`; every request to `/mcp` must send
`Authorization: Bearer <token>`. Only `GET /healthz` is open.

```bash
export MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
MCP_TRANSPORT=streamable-http uv run mcp-frankfurter      # or: make run-http
```

```bash
curl -i http://127.0.0.1:8000/healthz                 # 200 {"status":"ok"}
curl -i -X POST http://127.0.0.1:8000/mcp             # 401 {"error":"unauthorized",...}

curl -i -X POST http://127.0.0.1:8000/mcp \
  -H "Authorization: Bearer $MCP_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
# 200, an mcp-session-id header and the server's capabilities
```

With Docker (the image defaults to HTTP on `0.0.0.0:8000`):

```bash
docker build -t mcp-frankfurter .
docker run --rm -p 8000:8000 -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" mcp-frankfurter
# or, with the variables in .env:
cp .env.example .env && docker compose up --build
```

Put TLS in front (reverse proxy) before exposing it beyond localhost: the token travels in a
header.

## Configuration

Read from the environment, then from a `.env` file in the working directory (see `.env.example`).

| Variable | Default | Meaning |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http`. |
| `MCP_HOST` | `127.0.0.1` | Bind address for HTTP. `0.0.0.0` inside containers. |
| `MCP_PORT` | `8000` | Port for HTTP. |
| `MCP_AUTH_TOKEN` | — | Bearer token. **Required** when `MCP_TRANSPORT=streamable-http`. |
| `UPSTREAM_BASE_URL` | `https://api.frankfurter.dev/v2` | Frankfurter API base URL, version included; see `docs/DECISIONS.md`. |
| `HTTP_TIMEOUT_SECONDS` | `10` | Timeout per upstream request. |

## Tools

None registered yet. The Frankfurter tools (euro reference rates: latest, one historical date, a
date range, and the currency list — see `docs/DECISIONS.md`) land in the next development slice;
`docs/scenarios.md` is the catalogue they will be tagged against, and `tests/integration/
whitebox/test_catalogue_whitebox.py` proves the empty catalogue in the meantime.

Invalid input and upstream failures come back as MCP error results with a one-line message
(`ToolError`), never as a stack trace.

## Testing

```bash
uv run pytest -q                            # fast run; the live smoke test is deselected
uv run pytest -q --cov --cov-report=term-missing   # make test: adds the 100 % coverage gate
uv run python scripts/check_scenarios.py    # make scenarios: docs/scenarios.md vs both suites
uv run pytest -m live -q                    # one real call against the Frankfurter API (needs network)
uv run ruff check .                         # make lint (plus ruff format --check and mypy src)
uv run ruff format --check .
uv run mypy src
bash .claude/scripts/hex-check.sh           # all of the above plus the boundary checks
make mutation                               # mutmut on server/upstream/mappers, 0 survivors (Linux/WSL/Docker only)
```

Three kinds of test, per the `mcp-testing` skill:

- `tests/unit/` — mappers (once they exist), `Settings`, the composition root's wiring
  (`main()`, `get_client()`); **100 % line and branch coverage of `src/mcp_frankfurter`**
  (`fail_under = 100` in `pyproject.toml`, branch mode on) is the gate `make test` enforces; the
  only exclusion is the `if __name__ == "__main__":` guard. A number below 100 means a missing
  test, not a reason to lower the threshold.
- `tests/integration/whitebox/` — tools and `UpstreamClient` called directly, the upstream HTTP
  boundary mocked with `respx`; free to assert on what crossed that boundary (request params and
  headers, log content).
- `tests/integration/blackbox/` — only `Client(mcp, mode="legacy")` (the stdio shape, in memory)
  or the real HTTP app through `TestClient`; never a tool function or `UpstreamClient` directly.

Both integration suites are tagged with `@scenario("<ID>")` against the catalogue in
`docs/scenarios.md`; `make scenarios` fails when an ID is missing from either suite.
`tests/test_live.py` is the canary for the real API, marked `live` and deselected by
`pyproject.toml`.

Mutation testing (`make mutation`, `mutmut`) targets `server.py`, `upstream.py` and
`mappers.py` and must leave 0 unexplained survivors (`scripts/check_mutants.py`); a *provably
equivalent* mutant is listed in that script with a reason instead of chased with a pointless
test. `mutmut` does not run on Windows: use WSL, a Linux box, or the `mutation` CI job.

## Design notes

The server is a small hexagon: an MCP client drives it on the inbound side; it drives the
Frankfurter HTTP API on the outbound side. Each module has exactly one role; the `mcp-hexagonal`
skill carries the layer map and the recipe for adding a tool.

- **Ports and adapters.** `server.py` is the inbound adapter: it turns MCP tool calls into calls
  on the port, validates ranges and shapes what the model receives. `upstream.py` is the outbound
  adapter; the port is its public surface and everything about the wire lives behind it.
  `config.py` (settings) and `auth.py` (transport security) are infrastructure. `__main__.py` is
  the composition root: it builds `Settings`, injects the `UpstreamClient` and picks the
  transport. The dependency rule (`httpx` only in `upstream.py`, no URL in tools, no `mcp` import
  on the outbound side) is enforced by `.claude/scripts/hex-check.sh`: a boundary nobody checks
  erodes with the first hurried change.
- **Why the upstream client is the only file with URL shapes.** With paths, query parameters,
  headers, retries in one file and payload parsing delegated to `mappers.py`, the tests that
  target the outbound HTTP boundary (`respx`) keep proving the parser, the retry and the error
  mapping together. Tools never see `httpx`, so a fake or a second upstream is a drop-in.
- **Mappers own every boundary crossing.** `mappers.py` is, and will stay, the only module that
  turns an upstream payload into a typed record and a typed record into a tool DTO; it imports
  neither `httpx` nor `mcp`, so it is unit-tested on plain data, field by field, with no mock.
  `server.py` and `upstream.py` never build one of those literals themselves.
- **Error mapping for LLM consumers.** Every failure the model can act on is a `ToolError` with a
  one-line message naming the argument and the received value, or the failing dependency (e.g.
  `Frankfurter API unavailable: upstream returned HTTP 503`). The SDK returns it as an `is_error`
  result the model reads and reacts to: fix the argument, tell the user, try later. Bugs are not
  mapped: the model sees only `Error executing tool <name>` and the traceback goes to the server
  log, never to the client.
- **Auth models.** `stdio` trusts the parent process: the MCP client launched the server, as
  every desktop client does, so there is no token. `streamable-http` is network-reachable, so a
  bearer token is mandatory (the server refuses to start without one), compared in constant time
  by a pure-ASGI middleware that leaves streamed responses untouched; `GET /healthz` is the only
  open path. OAuth is the next seam, not a rewrite: `MCPServer(...)` accepts `auth=` and
  `token_verifier=`, and `build_http_app()` is the single place where the middleware is mounted.
  Tools and `upstream.py` do not change.
- **Configuration and lifecycle.** 12-factor: everything comes from the environment or `.env`,
  validated once at startup with fail-fast messages that never echo the input (secrets). The
  upstream client is created once in the composition root and closed by the server lifespan.

## Claude Code assets

`.claude/` ships project-level assets so Claude Code works inside the conventions above.

| Asset | What it does |
|---|---|
| `settings.json` | Allows `uv sync/lock`, `uv run pytest/ruff/mypy/mcp-frankfurter`, git reads and `docker build`; denies `rm -rf`, force pushes and reading `.env`. Hooks: `ruff` import sort and format after every Edit/Write (`scripts/format.sh`); a non-blocking reminder to run the checks on Stop while `src/` or `tests/` are dirty (`scripts/test-reminder.sh`). |
| `skills/mcp-hexagonal` | Layer map, dependency rule, how to add a tool end to end with file paths. |
| `skills/mcp-testing` | The unit/white-box/black-box split, the scenario catalogue, `respx` patterns, in-memory client session, the coverage and mutation gates, live smoke tests. |
| `agents/mcp-reviewer` | Read-only review: boundary, tool naming and descriptions, typed inputs, LLM-facing errors, secrets, auth, the scenario and mutation gates; findings by severity. |
| `agents/feature-planner` | Writes `docs/specs/<date>-<slug>.md` (tool contract, upstream contract, settings, errors, tests, files) before any code; creates `docs/specs/` on first use. |
| `/mcp-tool <name>` | Scaffolds mapper, upstream method, tool, tests in both suites, a scenario row and a README row; shows the plan and asks before writing. |
| `/hex-check [--no-tests]` | Runs `scripts/hex-check.sh` (boundaries, ruff, mypy, pytest) plus the scenario check, and summarises. |

## Layout

```
src/mcp_frankfurter/
  __main__.py   composition root: stdio, or uvicorn + auth middleware + /healthz
  auth.py       bearer-token ASGI middleware (infrastructure)
  config.py     Settings (pydantic-settings)
  mappers.py    payload <-> typed record <-> tool DTO, pure functions (empty for now)
  server.py     MCPServer instance and the tools (inbound adapter; no tool registered yet)
  upstream.py   the Frankfurter API client (outbound adapter)
docs/DECISIONS.md   the API version probe and the ECB working-day rule
docs/scenarios.md   the scenario catalogue; scripts/check_scenarios.py and check_mutants.py are
                    the gates that keep it and the mutation run honest
tests/
  unit/                settings, composition-root wiring; no Docker, no scenario IDs
  integration/whitebox/  tools + UpstreamClient called directly, respx-mocked
  integration/blackbox/  only Client(mcp, mode="legacy") or the real HTTP app
  test_live.py         opt-in canary against the real upstream API
.claude/        Claude Code settings, hooks, skills, agents, commands and the boundary checker
docs/specs/     feature specs; not shipped, the feature-planner agent creates it on first use
```

## License

MIT. See [`LICENSE`](LICENSE).
