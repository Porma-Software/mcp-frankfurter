# Decisions

## API version: v2, for every tool

Probed live against `https://api.frankfurter.dev` on 2026-09-11 (`curl`, no key needed):

| Need | `v2` (current) | `v1` (deprecated) |
|---|---|---|
| Latest rates | `GET /v2/rates?base=EUR` | `GET /v1/latest?base=EUR` |
| One historical date | `GET /v2/rates?date=YYYY-MM-DD&base=EUR` | `GET /v1/YYYY-MM-DD?base=EUR` |
| A date range | `GET /v2/rates?from=YYYY-MM-DD&to=YYYY-MM-DD&base=EUR` | `GET /v1/YYYY-MM-DD..YYYY-MM-DD?base=EUR` |
| Currency list | `GET /v2/currencies` | `GET /v1/currencies` |

`v2` supports all four, confirmed with live calls (`/v2/rates?base=EUR&quotes=USD,GBP,JPY`,
`/v2/rates?date=2026-09-06&base=EUR&quotes=ANG,GBP,USD` for the weekend date and
`/v2/rates?date=2026-09-08&base=EUR&quotes=USD,GBP,JPY` for the weekday,
`/v2/rates?from=2026-08-10&to=2026-09-08&base=EUR&quotes=USD`, `/v2/currencies`), so every tool
in this server uses `v2` — never a mix of `v1` and `v2`. `v1` was probed too, live, with its own
shapes (`/v1/latest`, `/v1/2026-09-06`, `/v1/2026-08-10..2026-09-08`, `/v1/currencies`) to
confirm the choice rather than assume it: `GET /v1` reports itself `"status":"deprecated"` (not
`"frozen"` as first assumed) and `GET /v2` `"status":"current"`; `v1`'s response nests every
quote currency's rate under one shared top-level `date`/`start_date`/`end_date`, and its
`/currencies` list is unnamed-by-code only (`{"USD":"United States Dollar", ...}`, no numeric
code, symbol or coverage dates) — coarser than `v2` on both counts, on top of `v2` already
covering every need on its own.

One quirk worth noting for the mapper: the query parameter for the quote currencies is `quotes`
(plural), not `quote` or `symbols` (`v1` uses `symbols`). A second, more consequential one:
`v2`'s `date` is per quote currency, not one date for the whole response — querying
`date=2026-09-06` (a Sunday) for `ANG,GBP,USD` together returns `GBP`/`USD` dated `2026-09-06`
but `ANG` still dated `2026-09-04` (its own last published day), all in the *same* JSON array;
`v1`'s equivalent single-date endpoint instead clamps the *whole* response to one shared date
(`2026-09-04` for that same weekend request). `mappers.py`'s `RateRow` keeps the `v2` per-row
`date`, and `to_rates_snapshot` surfaces the resulting per-currency mismatch in its `note` rather
than silently picking one row's date for the whole result — see `mappers.py` for detail.

`UPSTREAM_BASE_URL` (see `config.py`) defaults to `https://api.frankfurter.dev/v2` and is
overridable, so a pinned mirror or a future version needs no code change.

## ECB rates exist on working days only

The ECB publishes a reference rate once per working day; a request for a Saturday, Sunday or ECB
holiday gets back the most recent working day's rate instead of an error. Every tool result this
server returns carries the `rate_date` the upstream actually used, plus a plain-language note
whenever `rate_date` differs from the date the caller asked for — never a silent substitution.

## Upstream contract: client and mappers

`UpstreamClient.rates`/`.rates_range`/`.currencies` (`upstream.py`) and the domain records, tool
DTOs and pure `parse_*`/`to_*` functions between them (`mappers.py`) are built against the five
tools ops#7 specifies. `tests/fixtures/*.json` are the exact `curl` captures the probe above
used; the white-box suite replays them through `respx`, so the parser and the client are proven
against real upstream shapes without touching the network in CI.

## Tool catalogue: five `@mcp.tool()` functions in `server.py`

`convert`, `latest_rates`, `historical_rate`, `rate_timeseries` and `list_currencies` are thin
wrappers over `UpstreamClient` and `mappers.py` (see `docs/scenarios.md` for the FX-* scenario
catalogue). Every currency-code argument is upper-cased, trimmed and checked to be a 3-letter
code locally — never checked against the live currency catalogue first, since a syntactically
valid but unknown code is rejected by the upstream call itself (`UpstreamError` mapped to
`ToolError`), which needs no extra round trip to anticipate. `rate_timeseries` refuses a range
over 366 days or a `start_date` after `end_date` before ever calling upstream. `RatesSnapshot`
(shared by `latest_rates` and `historical_rate`) carries a `requested_date` field alongside
`rate_date` so `historical_rate` can echo back what was asked for; `latest_rates` always passes
`None`, since "latest" has no specific date to echo.

## A well-formed ISO 4217 code the ECB does not publish: an empty list, not an error

Confirmed live against `https://api.frankfurter.dev/v2` on 2026-09-12: a syntactically valid
3-letter code that passes this server's own `_currency_code` check but that the ECB does not
publish a reference rate for is not a `4xx`. `GET /v2/rates?base=EUR&quotes=XTS` and
`GET /v2/rates?base=XTS&quotes=USD` (`XTS` is ISO 4217's own code reserved for testing, never a
real currency) both come back `200` with an empty JSON array — the same shape Frankfurter uses
for "no rate published for the date/range asked", not a distinct "unknown currency" error.

`UpstreamClient` returns that empty list rather than raising `UpstreamError`, so `convert`,
`latest_rates`, `historical_rate` and `rate_timeseries` already handle it correctly with no
change needed: `to_conversion`/`to_rates_snapshot`/`to_rate_timeseries` raise `ValueError` on an
empty row list exactly as they do for a real currency pair with no data yet (see FX-07, FX-18,
FX-26, FX-30 in `docs/scenarios.md`), and each tool turns that into the same "no data available"
`ToolError` either way. This is correct, intended behaviour: to a caller, the ECB never having
tracked a currency looks identical to the ECB not having published for it yet.
