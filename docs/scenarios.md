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

Every currency code argument (`from_currency`, `to_currency`, `base`, `symbols`, `symbol`) is
upper-cased and trimmed before use, and validated to be a 3-letter code; the tools never check it
against the live currency catalogue (`list_currencies`) before calling upstream — the upstream
call itself rejects a syntactically valid but unknown code (see FX-04/11/17/25), which needs no
extra network round trip to anticipate.

## Currency conversion (`convert`)

| ID | Scenario | Expected outcome |
|---|---|---|
| FX-01 | A caller converts an amount with no `date` | The latest rate is used; `converted`, `rate` and `rate_date` (today's working day) come back, `note` is `null` |
| FX-02 | A caller converts an amount on a specific working-day `date` | `rate_date` equals the requested date; `note` is `null` |
| FX-03 | A caller converts an amount on a weekend or holiday `date` | The most recent working day's rate is used; `rate_date` differs from the requested date and `note` explains the substitution |
| FX-04 | `from_currency` or `to_currency` is not a 3-letter code | Validation error naming the argument and the value received; upstream is never called |
| FX-05 | `amount` is zero or negative | Validation error naming the value received; upstream is never called |
| FX-06 | `date` is not in `YYYY-MM-DD` format, or not a real calendar date | Validation error naming the value received; upstream is never called |
| FX-07 | Upstream has no data for the requested currency pair or date (e.g. a date before ECB coverage) | Error explaining no rate is available, naming the currencies and date |
| FX-08 | The upstream is unreachable or answers with an error status | Error naming the exchange-rate service as unavailable |

## Latest rates (`latest_rates`)

| ID | Scenario | Expected outcome |
|---|---|---|
| FX-09 | A caller asks for the latest rates with the default `base` and no `symbols` | Every currency Frankfurter tracks against EUR comes back, dated the latest published day |
| FX-10 | A caller restricts `symbols` to a subset of currencies | Only those currencies come back |
| FX-11 | `base` or an entry of `symbols` is not a 3-letter code | Validation error naming the argument and the value received; upstream is never called |
| FX-12 | The upstream is unreachable or answers with an error status | Error naming the exchange-rate service as unavailable |
| FX-30 | Upstream has no rates at all for the requested base/symbols | Error explaining no rates are available, naming the base currency |

## Historical rate (`historical_rate`)

| ID | Scenario | Expected outcome |
|---|---|---|
| FX-13 | A caller looks up a working-day `date` | `requested_date` equals `rate_date`; `note` is `null` |
| FX-14 | A caller looks up a weekend or holiday `date` | The most recent working day's rate is used; `rate_date` differs from `requested_date` and `note` explains the substitution |
| FX-15 | One of the requested currencies' own feed lags the rest (a per-currency stale rate, `v2`'s own quirk — see `docs/DECISIONS.md`) | `rate_date` is the most recent date among the rates returned; `note` names the lagging currency and its own (older) date |
| FX-16 | `date` is not in `YYYY-MM-DD` format, or not a real calendar date | Validation error naming the value received; upstream is never called |
| FX-17 | `base` or an entry of `symbols` is not a 3-letter code | Validation error naming the argument and the value received; upstream is never called |
| FX-18 | Upstream has no data at all for the requested date (e.g. long before ECB coverage) | Error explaining no rate is available, naming the base currency and date |
| FX-19 | The upstream is unreachable or answers with an error status | Error naming the exchange-rate service as unavailable |

## Rate history (`rate_timeseries`)

| ID | Scenario | Expected outcome |
|---|---|---|
| FX-20 | A caller asks for a valid range | One point per working day published in the range, plus `min`, `max` and `average` across those points |
| FX-21 | A caller omits `base` and `symbol` | Defaults to `EUR` against `USD` |
| FX-22 | `start_date` is after `end_date` | Validation error naming both dates; upstream is never called |
| FX-23 | The range from `start_date` to `end_date` is longer than 366 days | Validation error naming the number of days received; upstream is never called |
| FX-24 | `start_date` or `end_date` is not in `YYYY-MM-DD` format, or not a real calendar date | Validation error naming the value received; upstream is never called |
| FX-25 | `base` or `symbol` is not a 3-letter code | Validation error naming the argument and the value received; upstream is never called |
| FX-26 | The range is valid but upstream has no published rate anywhere inside it | Error explaining no data is available, naming the currency and the range |
| FX-27 | The upstream is unreachable or answers with an error status | Error naming the exchange-rate service as unavailable |

## Currency catalogue (`list_currencies`)

| ID | Scenario | Expected outcome |
|---|---|---|
| FX-28 | A caller lists the supported currencies | Every currency Frankfurter tracks comes back with its ISO 4217 code and name |
| FX-29 | The upstream is unreachable or answers with an error status | Error naming the currency-catalogue service as unavailable |

## Tool catalogue

| ID | Scenario | Expected outcome |
|---|---|---|
| SRV-01 | A client lists the available tools | Exactly `convert`, `latest_rates`, `historical_rate`, `rate_timeseries` and `list_currencies`, with their documented input and output schemas |

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
