# Decisions

## API version: v2, for every tool

Probed live against `https://api.frankfurter.dev` on 2026-09-11 (`curl`, no key needed):

| Need | `v2` (current) | `v1` (frozen) |
|---|---|---|
| Latest rates | `GET /v2/rates?base=EUR` | `GET /v1/latest?base=EUR` |
| One historical date | `GET /v2/rates?date=YYYY-MM-DD&base=EUR` | `GET /v1/YYYY-MM-DD?base=EUR` |
| A date range | `GET /v2/rates?from=YYYY-MM-DD&to=YYYY-MM-DD&base=EUR` | `GET /v1/YYYY-MM-DD..YYYY-MM-DD?base=EUR` |
| Currency list | `GET /v2/currencies` | `GET /v1/currencies` |

`v2` supports all four, confirmed with live calls (`/v2/rates?base=EUR&quotes=USD`,
`/v2/rates?date=2026-09-06&base=EUR&quotes=USD`,
`/v2/rates?from=2026-08-01&to=2026-08-10&base=EUR&quotes=USD`, `/v2/currencies`), so every tool
in this server uses `v2` — never a mix of `v1` and `v2`. One quirk worth noting for the mapper
that lands in the next slice: the query parameter for the quote currencies is `quotes` (plural),
not `quote` or `symbols`; `GET /v2` itself confirms the version as `"status":"current"` and
`GET /v1` as `"status":"frozen"`.

`UPSTREAM_BASE_URL` (see `config.py`) defaults to `https://api.frankfurter.dev/v2` and is
overridable, so a pinned mirror or a future version needs no code change.

## ECB rates exist on working days only

The ECB publishes a reference rate once per working day; a request for a Saturday, Sunday or ECB
holiday gets back the most recent working day's rate instead of an error. Every tool result this
server returns carries the `rate_date` the upstream actually used, plus a plain-language note
whenever `rate_date` differs from the date the caller asked for — never a silent substitution.
