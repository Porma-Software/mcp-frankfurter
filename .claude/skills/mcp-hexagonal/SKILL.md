---
name: mcp-hexagonal
description: Use when adding or changing a tool, the upstream client, settings or the transport of this MCP server, or when unsure which module owns a change. Layer map, dependency rule and the end-to-end recipe for a new tool with file paths.
---

# MCP server as ports and adapters

The server is a thin hexagon: an MCP client drives it (inbound), it drives an upstream HTTP API
(outbound). Every module has exactly one role.

| Module | Role | Owns | Must not |
|---|---|---|---|
| `src/mcp_frankfurter/server.py` | Inbound adapter (MCP tools) + application logic | tool names, argument schemas, docstrings the model reads, range validation, `ToolError` mapping | build URLs, import `httpx`, parse upstream payloads, build a `Place`/`DailyForecast` literal |
| `src/mcp_frankfurter/upstream.py` | Outbound adapter (HTTP client) | URL shapes, params, headers, timeout, retry, `UpstreamError` | import `mcp`, know about tools or transports, build a `GeoMatch`/`DailyRow` literal |
| `src/mcp_frankfurter/mappers.py` | Boundary mapping (pure functions) | payload -> typed record (`parse_geo_match`, `parse_daily_rows`), record -> tool DTO (`to_place`, `to_daily_forecast` and their list forms), the `Place`/`DailyForecast`/`GeoMatch`/`DailyRow` types themselves | import `httpx` or `mcp`; every function here is a pure data transform, unit-tested without a mock |
| `src/mcp_frankfurter/config.py` | Infrastructure: configuration | `Settings` (env + `.env`), `SecretStr` secrets, invariants (HTTP needs a token) | import anything from the other modules |
| `src/mcp_frankfurter/auth.py` | Infrastructure: transport security | bearer-token ASGI middleware, exempt paths | know about tools |
| `src/mcp_frankfurter/__main__.py` | Composition root | builds `Settings`, injects `UpstreamClient` via `set_client`, picks the transport, mounts `/healthz` and the middleware | contain business rules |

The **port** between the two sides is the public surface of `UpstreamClient`: plain-argument
methods (`geocode(name, count)`, `forecast(latitude, longitude, days)`) returning typed records
(`GeoMatch`, `DailyRow`) or raising `UpstreamError`. Tools depend on that surface only, so a
different upstream (or a fake) is a drop-in replacement of one file; only `mappers.py` needs to
learn the new record shape.

## Dependency rule

```
__main__.py -> server.py -> upstream.py -> httpx
     |             |             |    \
     +-> auth.py   +-> config.py <+    -> mappers.py <-+ (both sides map through here)
```

- Arrows point inwards; nothing imports `server.py` except `__main__.py` and the tests.
- `httpx` appears in `upstream.py` only. `mcp` appears in `server.py` and `__main__.py` only.
  `mappers.py` imports neither: it is plain Python, unit-tested on plain data.
- Tools get the client through `get_client()`; never instantiate `UpstreamClient` in a tool.
- Tools return `to_places(...)`/`to_daily_forecasts(...)`; they never build a DTO literal inline.
- `bash .claude/scripts/hex-check.sh` enforces the three greps plus ruff, mypy and pytest.

## Add a tool end to end

Example: `get_air_quality(latitude, longitude)`.

1. **Boundary types and parser**, `src/mcp_frankfurter/mappers.py`
   - A frozen dataclass for the upstream record (`AirQualityRow(date: str, pm10: float | None,
     ...)`) and a `TypedDict` for the tool DTO (`AirQuality`).
   - `parse_air_quality(payload) -> AirQualityRow`, raising `ValueError` on a malformed shape,
     and `to_air_quality(row) -> AirQuality` / `to_air_qualities(rows) -> list[AirQuality]`.
2. **Outbound method**, `src/mcp_frankfurter/upstream.py`
   - `async def air_quality(self, latitude: float, longitude: float) -> list[AirQualityRow]`
     calling `self._get_json(f"{self._base_url}/v1/air-quality", {...})`, then
     `parse_air_quality` per item; wrap its `ValueError` as `UpstreamError(str(exc))`.
   - A new base URL or key? Add a field to `Settings` (`config.py`, `SecretStr` if secret), read
     it in `UpstreamClient.from_settings`, document it in `.env.example` and the README table.
3. **Inbound tool**, `src/mcp_frankfurter/server.py`
   - `@mcp.tool()` `async def get_air_quality(latitude: Annotated[float, Field(description=...)], ...)`.
     The docstring is for the model: when to use it, what it returns, units, edge cases.
   - Validate ranges first: `raise ToolError("latitude must be between -90 and 90, got 91")`.
   - Wrap the port: `except UpstreamError as exc: log.warning(...);
     raise ToolError(f"air quality service unavailable: {exc}") from exc`; return
     `to_air_qualities(rows)`.
   - Update `instructions=` in `MCPServer(...)` when the new tool changes the recommended flow.
4. **Docs first**: a row per scenario (happy path and every failure path) in `docs/scenarios.md`.
5. **Tests**: `tests/unit/test_mappers.py` (parser + DTO mapping, field by field); a tagged test
   per new scenario ID in `tests/integration/whitebox/` (call the tool directly) and in
   `tests/integration/blackbox/` (through `Client(mcp, mode="legacy")`); `TOOL_NAMES` in both
   suites' catalogue tests. See the `mcp-testing` skill. `make scenarios` must stay green.
6. **Samples**, `tests/samples.py`: a trimmed real payload plus the expected tool output.
7. **Docs**: README tools table and configuration table.
8. `bash .claude/scripts/hex-check.sh`; if `upstream.py`, `server.py` or `mappers.py` changed,
   also run `make mutation` (Linux/WSL/CI only) before a PR — see the `mcp-testing` skill.

## Error mapping (what the model sees)

| Condition | Raise | Client receives |
|---|---|---|
| Bad argument (range, empty string) | `ToolError("count must be between 1 and 10, got 0")` | `is_error=True`, the message, no traceback |
| Upstream 4xx/5xx, timeout, bad JSON | `UpstreamError` in `upstream.py`, wrapped by the tool as `ToolError("<service> unavailable: <why>")` | same |
| Anything else (a bug) | uncaught | `Error executing tool <name>`; the traceback only reaches the server log |

Messages name the argument and the received value so the model can correct its next call.

## Transport and auth are pluggable

`stdio` trusts the parent process (no token). `streamable-http` wraps the SDK app with
`BearerTokenMiddleware` in `build_http_app()`. OAuth later: pass `auth=` and `token_verifier=`
to `MCPServer(...)` and drop the middleware; tools and `upstream.py` do not change.
