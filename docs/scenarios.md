# Scenario catalogue

The contract between the two integration suites. One row per user scenario, happy and failure
paths alike; `make scenarios` fails when an ID is missing from either suite.

- **White-box** (`tests/integration/whitebox/`) drives the ports and adapters directly: the tool
  functions and the `UpstreamClient` in-process, with the upstream HTTP boundary mocked
  (`respx`). It may assert on what crossed that boundary — the request sent to the upstream API,
  a raised `UpstreamError`/`ValueError`, a middleware's internal decision.
- **Black-box** (`tests/integration/blackbox/`) only uses the public MCP surface, as a client
  would: a real client session over in-memory streams with JSON-RPC framing
  (`mcp.client.Client(mcp, mode="legacy")`, the stdio shape) or the streamable-HTTP transport
  through `TestClient`. It never calls a tool function or `UpstreamClient` directly, and never
  inspects an internal record — only tool results, HTTP status codes and bodies. The one thing it
  cannot avoid mocking is the upstream network call itself (`respx`): there is no client-facing
  way to serve a fixed rates payload otherwise, and `tests/test_live.py` (marked `live`,
  deselected by default) is the canary that keeps that mock honest against the real API.

Every test in both suites is tagged with `@scenario("<ID>", ...)` (`tests/integration/
scenarios.py`).

## Scope

Server-level behaviour without a user-facing scenario (the composition root wiring, which
transport `main()` starts, `Settings` validation rules, the shape of a bug — as opposed to a
handled failure — reaching the client) is covered by `tests/unit/` and deliberately carries no
catalogue ID: it has no black-box counterpart, because there is no *user* action attached to it.

AUTH-05 (a `stdio` session needs no token at all) has, for now, a dedicated white-box test
(`tests/integration/whitebox/test_catalogue_whitebox.py`) instead of being tagged onto an
existing tool test: no tool is registered yet in this scaffold slice (see `docs/DECISIONS.md`),
so there is nothing else to piggyback the tag on. Once the Frankfurter tools land, `make
scenarios` still only requires AUTH-05 to be tagged somewhere in the white-box suite — moving the
tag onto a tool test instead of keeping this dedicated one is a valid way to satisfy it, exactly
as any white-box test already calls a tool function directly with no `BearerTokenMiddleware` in
front of it, which *is* the white-box shape of "no token required in-process".

## Frankfurter tools

No tool is registered yet. The next development slice adds the tool catalogue here — one table
per tool, one row per happy and failure path — following `.claude/skills/mcp-hexagonal/SKILL.md`
and this catalogue's own "Adding a scenario" section below.

## Authentication (streamable-HTTP transport)

| ID | Scenario | Expected outcome |
|---|---|---|
| AUTH-01 | An HTTP request to `/mcp` carries no `Authorization` header | 401, `WWW-Authenticate: Bearer`; the tool never runs |
| AUTH-02 | An HTTP request carries the wrong token, a malformed header or a different auth scheme | 401, same as AUTH-01 |
| AUTH-03 | An HTTP request carries the correct bearer token | The request passes through: the initialize handshake succeeds and the server identifies itself |
| AUTH-04 | Any transport: `GET /healthz` | 200, open, no token required |
| AUTH-05 | A client connects without HTTP at all (the `stdio` shape: an in-memory session with no bearer layer) | Tools work with no token — `stdio` trusts the parent process that launched the server |

## Adding a scenario

1. Add the row here with the next free ID.
2. Tag a white-box test in `tests/integration/whitebox/` with `@scenario("<ID>")`.
3. Tag a black-box test in `tests/integration/blackbox/` with `@scenario("<ID>")`.
4. `make scenarios` (also runs in CI) must stay green.
