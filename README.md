# mcp-frankfurter

Official euro exchange rates, answered inside a Claude conversation — no spreadsheet, no
currency-converter tab, no manual lookup.

This is an [MCP](https://modelcontextprotocol.io) server: a small connector that gives Claude
five new abilities, all backed by the [Frankfurter API](https://frankfurter.dev), which publishes
the European Central Bank's official daily reference rates and needs no account or API key.

## What your team can do with this in Claude

Once it is connected, ask Claude things like:

- "Convert 1,500 EUR to US dollars and British pounds at today's ECB rate."
- "What was the euro-to-dollar rate on 6 March 2026?"
- "How has the pound sterling moved against the euro over the last 30 days — trending up or down?"
- "Which currencies does the ECB publish an official reference rate for?"
- "We invoiced a UK client in GBP on their invoice date — what's that worth in EUR at today's rate for comparison?"

Claude picks the right tool, calls the Frankfurter API, and answers in plain language — citing the
exact date the rate was published.

## See it working

![A terminal recording of the demo script asking for the latest USD and GBP rates, converting 1,500 EUR to USD, and pulling a 30-day rate history for GBP.](docs/demo.gif)

The recording runs [`scripts/demo.py`](scripts/demo.py), a plain MCP client talking to this
server exactly as Claude would: latest rates for USD and GBP, converting 1,500 EUR to USD, and a
30-day rate history — real calls, real answers.

## Set up in 5 minutes

You need [`uv`](https://docs.astral.sh/uv/) installed (or Docker, see below), and an MCP client
such as [Claude Desktop](https://claude.ai/download) or [Claude Code](https://claude.com/claude-code).

### Claude Desktop or Claude Code, over stdio (individual use)

Add this to Claude Desktop's config file (macOS: `~/Library/Application Support/Claude/
claude_desktop_config.json`, Windows: `%APPDATA%\Claude\claude_desktop_config.json`) or to a
project's `.mcp.json` for Claude Code, then restart the client:

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Porma-Software/mcp-frankfurter", "mcp-frankfurter"]
    }
  }
}
```

`uvx` downloads and runs the server on demand — nothing to install ahead of time. No API key,
no account, no configuration needed for this mode: it talks to Claude over stdin/stdout, and to
Frankfurter's public API over plain HTTPS.

### Docker, over stdio

```bash
docker build -t mcp-frankfurter https://github.com/Porma-Software/mcp-frankfurter.git
```

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "MCP_TRANSPORT=stdio", "mcp-frankfurter"]
    }
  }
}
```

(The image defaults to the HTTP transport, so stdio use overrides `MCP_TRANSPORT` back to `stdio`.)

### Running it for a whole team, over HTTP

For several people sharing one server, run it as a long-lived HTTP service protected by a bearer
token instead of a client launching its own copy:

```bash
export MCP_AUTH_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker run -d --name mcp-frankfurter -p 8000:8000 -e MCP_AUTH_TOKEN="$MCP_AUTH_TOKEN" \
  mcp-frankfurter
```

Put it behind TLS (a reverse proxy) before it leaves localhost — the token travels in a header.
Each team member then points their client at it:

```json
{
  "mcpServers": {
    "mcp-frankfurter": {
      "type": "http",
      "url": "https://mcp-frankfurter.your-domain.example/mcp",
      "headers": { "Authorization": "Bearer <the token above>" }
    }
  }
}
```

## What it does not do

- **No trading advice.** It reports published rates; it does not recommend when to buy, sell or
  hedge a currency.
- **No intraday rates.** The ECB publishes one reference rate per working day (around 16:00 CET),
  not a live, minute-by-minute market feed — do not use it for a trading desk.
- **ECB working days only.** No rate publishes on weekends or ECB holidays; a request for one of
  those dates gets back the most recent working day's rate instead, with a note explaining the
  substitution — never a silent guess.
- **A limited currency list.** Frankfurter tracks the major currencies the ECB itself publishes
  against the euro (around 30) — not every ISO 4217 code in the world. Ask
  `list_currencies` to see the exact set.

## Data and privacy

The only network call this server makes is the query to the public Frankfurter API
(`api.frankfurter.dev`) — an amount and a couple of currency codes, nothing more. No API key, no
account, no personal data of any kind is collected, stored or sent anywhere. Nothing about your
Claude conversation reaches Frankfurter, and nothing about your exchange-rate queries reaches
anyone but Frankfurter.

## For developers

A small hexagon: `server.py` is the inbound MCP adapter (five tools — `convert`, `latest_rates`,
`historical_rate`, `rate_timeseries`, `list_currencies`), `upstream.py` is the outbound Frankfurter
HTTP client, and `mappers.py` is the only module that turns a raw payload into a typed record and
a typed record into a tool result — see [`.claude/skills/mcp-hexagonal/SKILL.md`](.claude/skills/mcp-hexagonal/SKILL.md)
for the full layer map and [`docs/DECISIONS.md`](docs/DECISIONS.md) for the API version chosen and
why.

```bash
uv sync                                            # install (Python 3.14, .python-version)
uv run pytest -q --cov --cov-report=term-missing   # unit + white-box + black-box, no network
uv run python scripts/check_scenarios.py           # docs/scenarios.md vs both integration suites
uv run ruff check . && uv run ruff format --check . && uv run mypy src
make mutation                                      # mutmut, 0 survivors (Linux/WSL/CI only)
docker build -t mcp-frankfurter .
```

- **Tests.** Three suites per [`.claude/skills/mcp-testing/SKILL.md`](.claude/skills/mcp-testing/SKILL.md):
  `tests/unit/` (mappers, settings, composition-root wiring), `tests/integration/whitebox/`
  (tools and the upstream client called directly, `respx`-mocked), `tests/integration/blackbox/`
  (only the public MCP surface — an in-memory client session or the real HTTP app). Every
  user-facing scenario in [`docs/scenarios.md`](docs/scenarios.md) is tagged in both integration
  suites; `scripts/check_scenarios.py` fails the build if one is missing from either.
  `tests/test_live.py` is an opt-in canary against the real API (`uv run pytest -m live`), never
  run in CI.
- **Coverage.** 100 % line and branch coverage of `src/mcp_frankfurter`, enforced by
  `fail_under = 100` in `pyproject.toml`.
- **Mutation testing.** `mutmut` targets `server.py`, `upstream.py` and `mappers.py` and must
  leave zero unexplained survivors (`scripts/check_mutants.py`); a documented, provably
  equivalent mutant is the only allowed exception. `mutmut` does not run on Windows — use WSL, a
  Linux box, or CI's own `mutation` job.
- **CI.** GitHub Actions runs lint, the scenario check, the full test suite and a Docker build on
  every push and pull request, plus a separate mutation-testing job — see
  [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

## Built by Porma Software

Built and maintained by Porma Software as an open-source reference server.

## License

MIT. See [`LICENSE`](LICENSE).
