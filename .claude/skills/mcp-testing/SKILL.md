---
name: mcp-testing
description: Use when writing or fixing tests for this MCP server: the unit/white-box/black-box split, the scenario catalogue, respx fixtures, the in-memory client session, the 100 % line+branch coverage gate, the mutation gate, and the live smoke tests that stay deselected by default.
---

# Testing the MCP server

No test touches the network unless it is marked `live`. `uv run pytest -q` runs everything else;
`make test` adds the gate: **100 % line and branch coverage of `src/mcp_frankfurter`**, so a new
branch without a test fails the build. Coverage below 100 % means a missing test, never a
lower `fail_under`; the only exclusion is the `if __name__ == "__main__":` guard.

## Three kinds of test

| Kind | Where | Covers |
|---|---|---|
| Unit | `tests/unit/` | `mappers.py` field by field, `Settings`, composition-root wiring (`main()`) — no user scenario of its own |
| White-box | `tests/integration/whitebox/` | tools and `UpstreamClient` called directly, `respx`-mocked; may assert what crossed the boundary (request params/headers, log content) |
| Black-box | `tests/integration/blackbox/` | only `Client(mcp, mode="legacy")` or the real HTTP app; never a tool function or `UpstreamClient` directly |

Every user-facing behaviour (a tool's happy/failure paths, an auth outcome) is a row in
`docs/scenarios.md` with a unique ID, tagged with `@scenario("<ID>")`
(`tests/integration/scenarios.py`) on a test in **both** the white-box and the black-box suite.
`make scenarios` (`scripts/check_scenarios.py`) collects both suites and fails when an ID is
missing from either — read it before adding a scenario.

## Pin the outcome, not the call

A test that runs code without asserting an observable outcome is a defect. In particular:
`pytest.raises(Err, match="a substring")` still matches mutmut's mutated `"XX<literal>XX"`
string — the substring survives inside it — so it proves nothing about that literal. Assert the
**full** message (`str(exc.value) == "..."`) or the **full** log line (`msg in caplog.messages`,
not `in caplog.text`, which is substring search over the whole buffer).

## Fixtures (`tests/conftest.py`)

- `_clean_environment` (autouse) removes every `MCP_*` / `UPSTREAM_*` variable so a developer's
  shell cannot leak into a test. Construct settings as `Settings(_env_file=None, ...)`.
- `upstream_client` (autouse) injects a fresh `UpstreamClient` with `server.set_client()` and
  closes it afterwards, so tools never see a stale client.
- `respx_mock` (from respx) is the router; while active, unmatched requests fail instead of
  reaching the network. Black-box tests use it too — mocking the upstream network call is
  unavoidable (no real weather API in CI) — but never mock the tool or `UpstreamClient` itself.

## respx patterns

```python
@pytest.fixture
def forecast_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(FORECAST_URL)

forecast_route.mock(return_value=httpx.Response(200, json=FORECAST_RESPONSE))   # happy path
forecast_route.mock(return_value=httpx.Response(503, json={"reason": "nope"}))  # upstream error
forecast_route.side_effect = [httpx.ConnectError("refused"), httpx.Response(200, json=...)]
forecast_route.side_effect = httpx.ReadTimeout("slow")                          # not retried
assert forecast_route.calls.last.request.url.params["forecast_days"] == "3"     # white-box only
assert not forecast_route.called                                                # validation first
```

Payloads live in `tests/samples.py`: a trimmed copy of a real response next to the expected tool
output. Capture a new one with `curl`; keep the fields the parser reads plus one it ignores.

## In-memory client session (black-box)

```python
async with Client(mcp, mode="legacy") as client:
    result = await client.call_tool("geocode_place", {"name": "León", "count": 2})
assert result.is_error is False
assert result.structured_content == {"result": EXPECTED_PLACES}
```

`mode="legacy"` runs the server behind in-memory streams with JSON-RPC framing and the
initialize handshake, the path a stdio or HTTP client takes — and the shape AUTH-05 in
`docs/scenarios.md` points at: no bearer layer sits in front of it, same as a stdio session.
The default `"auto"` mode dispatches in-process without serialising and would hide schema
regressions.

## Auth tests

White-box drives `BearerTokenMiddleware` directly over a bare ASGI app. Black-box uses
`starlette.testclient.TestClient` over the real app: build one per module with
`Settings(_env_file=None, mcp_transport="streamable-http", mcp_auth_token=TOKEN)` and
`build_http_app` — the SDK session manager can only be started once per `MCPServer`. Send
`Accept: application/json, text/event-stream` with `initialize`; assert `mcp-session-id` on 200.

## Mutation gate

`make mutation` runs `mutmut` over `server.py`, `upstream.py` and `mappers.py`
(`[tool.mutmut]` in `pyproject.toml`) and must leave 0 unexplained survivors
(`scripts/check_mutants.py`). It refuses to run on Windows: use WSL or a Linux container
(`ghcr.io/astral-sh/uv:python3.14-bookworm-slim`, project copied in — never bind-mount `.venv`
across platforms) or let CI's `mutation` job run it. A survivor means fix the test; only a
*provably equivalent* mutant (e.g. `.rstrip("/")` vs `.rstrip("XX/XX")` — `rstrip` strips a
**character set**, and `/` stays in that set either way) goes in `EQUIVALENT_MUTANTS`, with why.

## What to mock, what not

- Mock the upstream HTTP boundary only (respx). Never mock `UpstreamClient` methods or a tool
  function: the tests must prove the parser, the retry and the error mapping together.
- Do not mock the MCP SDK; use the in-memory client above.
- Settings tests use `monkeypatch.setenv` and `tmp_path`, never real files.

## Live smoke test

`tests/test_live.py` calls the real upstream once per endpoint and is marked `live`;
`pyproject.toml` deselects it (`addopts = "-m 'not live'"`). Run it after changing `upstream.py`
or `mappers.py`, or before a release: `uv run pytest -m live -q`. Keep it out of CI.
