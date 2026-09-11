# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""The MCP server: tool definitions on top of the upstream client.

Five thin `@mcp.tool()` functions (`convert`, `latest_rates`, `historical_rate`,
`rate_timeseries`, `list_currencies`) wrap `UpstreamClient` (see `docs/DECISIONS.md` for the
chosen API version) through the pure `parse_*`/`to_*` functions in `mappers.py`, following
`.claude/skills/mcp-hexagonal/SKILL.md`: every tool validates its own arguments (currency-code
shape, date format, range limits) before ever calling upstream, then maps the result — never a
DTO literal built inline here.
"""

import logging
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date as date_type
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from mcp_frankfurter.config import Settings
from mcp_frankfurter.mappers import (
    Conversion,
    Currency,
    RatesSnapshot,
    RateTimeseries,
    to_conversion,
    to_currencies,
    to_rate_timeseries,
    to_rates_snapshot,
)
from mcp_frankfurter.upstream import UpstreamClient, UpstreamError

log = logging.getLogger(__name__)

SERVER_NAME = "mcp-frankfurter"
# ECB reference rates: refuse a rate_timeseries range longer than this many days.
MAX_RANGE_DAYS = 366

_CURRENCY_CODE_RE = re.compile(r"^[A-Za-z]{3}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

__all__ = [
    "MAX_RANGE_DAYS",
    "SERVER_NAME",
    "convert",
    "historical_rate",
    "latest_rates",
    "list_currencies",
    "mcp",
    "rate_timeseries",
]


# Upstream client shared by the tools. main() injects one built from the validated Settings;
# tests inject their own; anything else gets a lazily built default.
_client: UpstreamClient | None = None


def get_client() -> UpstreamClient:
    global _client
    if _client is None:
        _client = UpstreamClient.from_settings(Settings())
    return _client


def set_client(client: UpstreamClient | None) -> None:
    global _client
    _client = client


async def close_client() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()


@asynccontextmanager
async def _lifespan(_: "MCPServer[None]") -> AsyncIterator[None]:
    try:
        yield
    finally:
        await close_client()


# Transport options (host, port, DNS-rebinding guard) belong to the transport, not to the server:
# see build_http_app() in __main__.py.
mcp: "MCPServer[None]" = MCPServer(
    SERVER_NAME,
    instructions=(
        "Euro reference exchange-rate tools backed by the Frankfurter API (ECB data). Use "
        "convert to turn an amount from one currency into another; latest_rates or "
        "historical_rate for a base currency's rates as of today or a specific date; "
        "rate_timeseries to track one currency pair across a date range; and list_currencies "
        "to check which ISO 4217 codes are supported. ECB reference rates publish on working "
        "days only: every result names the date it actually used (rate_date) and explains any "
        "substitution in its note."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------------------------
# Argument validation. Raises ToolError so a non-developer reads a message naming the argument
# and the value that was wrong; upstream is never called when one of these fails.
# ---------------------------------------------------------------------------------------------


def _currency_code(value: str, *, field: str) -> str:
    code = value.strip().upper()
    if not _CURRENCY_CODE_RE.fullmatch(code):
        raise ToolError(f"{field} must be a 3-letter ISO 4217 currency code, got {value!r}")
    return code


def _currency_codes(values: list[str] | None, *, field: str) -> list[str] | None:
    if values is None:
        return None
    if not values:
        raise ToolError(f"{field} must not be an empty list; omit it to include every currency")
    return [_currency_code(value, field=field) for value in values]


def _iso_date(value: str, *, field: str) -> date_type:
    if not _DATE_RE.fullmatch(value):
        raise ToolError(f"{field} must be a date in YYYY-MM-DD format, got {value!r}")
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise ToolError(f"{field} must be a valid calendar date, got {value!r}") from None


# ---------------------------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------------------------


@mcp.tool()
async def convert(
    amount: Annotated[
        float,
        Field(description="Amount of money to convert, in from_currency units. Must be positive."),
    ],
    from_currency: Annotated[
        str, Field(description="Currency to convert from, as a 3-letter ISO 4217 code, e.g. 'USD'.")
    ],
    to_currency: Annotated[
        str, Field(description="Currency to convert to, as a 3-letter ISO 4217 code, e.g. 'EUR'.")
    ],
    date: Annotated[
        str | None,
        Field(
            description="Date to use for the exchange rate, as YYYY-MM-DD. Omit to use the "
            "latest available rate."
        ),
    ] = None,
) -> Conversion:
    """Convert an amount from one currency to another at the ECB reference rate.

    Returns the converted amount, the rate applied and the date it was published (`rate_date`).
    ECB reference rates publish on working days only: if `date` falls on a weekend or a holiday,
    the most recent working day's rate is used instead, and `note` explains the substitution in
    plain language.
    """
    if amount <= 0:
        raise ToolError(f"amount must be positive, got {amount}")
    base = _currency_code(from_currency, field="from_currency")
    quote = _currency_code(to_currency, field="to_currency")
    if date is not None:
        _iso_date(date, field="date")
    try:
        rows = await get_client().rates(base=base, quotes=[quote], date=date)
    except UpstreamError as exc:
        log.warning("convert(%s, %s, %s, date=%s) failed: %s", amount, base, quote, date, exc)
        raise ToolError(f"exchange rate service unavailable: {exc}") from exc
    try:
        return to_conversion(rows, amount=amount, quote=quote, requested_date=date)
    except ValueError as exc:
        raise ToolError(
            f"no exchange rate available from {base} to {quote}"
            + (f" on {date}" if date is not None else "")
            + ": the ECB may not track this currency, or has not published a rate for that date"
        ) from exc


@mcp.tool()
async def latest_rates(
    base: Annotated[
        str,
        Field(description="Currency every rate is quoted against, as a 3-letter ISO 4217 code."),
    ] = "EUR",
    symbols: Annotated[
        list[str] | None,
        Field(
            description="Currencies to include, as 3-letter ISO 4217 codes. Omit to return "
            "every currency Frankfurter tracks."
        ),
    ] = None,
) -> RatesSnapshot:
    """The latest published ECB reference rates for one base currency.

    Returns one rate per requested currency (or every currency Frankfurter tracks, when
    `symbols` is omitted), plus the date those rates were published (`rate_date`). ECB rates
    publish on working days only, so `note` explains it when one currency's own feed lags behind
    the rest of the snapshot.
    """
    base_code = _currency_code(base, field="base")
    quote_codes = _currency_codes(symbols, field="symbols")
    try:
        rows = await get_client().rates(base=base_code, quotes=quote_codes)
    except UpstreamError as exc:
        log.warning("latest_rates(%s, symbols=%s) failed: %s", base_code, quote_codes, exc)
        raise ToolError(f"exchange rate service unavailable: {exc}") from exc
    try:
        return to_rates_snapshot(rows)
    except ValueError as exc:
        raise ToolError(f"no exchange rates available for base currency {base_code}") from exc


@mcp.tool()
async def historical_rate(
    date: Annotated[str, Field(description="Date to look up, as YYYY-MM-DD.")],
    base: Annotated[
        str,
        Field(description="Currency every rate is quoted against, as a 3-letter ISO 4217 code."),
    ] = "EUR",
    symbols: Annotated[
        list[str] | None,
        Field(
            description="Currencies to include, as 3-letter ISO 4217 codes. Omit to return "
            "every currency Frankfurter tracks."
        ),
    ] = None,
) -> RatesSnapshot:
    """ECB reference rates for one base currency on a specific date.

    Returns the date that was requested (`requested_date`), the date the rates actually
    published on (`rate_date`) and one rate per requested currency. ECB rates publish on working
    days only: a weekend or holiday `date` returns the most recent working day's rate instead of
    an error, and `note` explains the substitution — including when one currency's own feed lags
    the rest.
    """
    base_code = _currency_code(base, field="base")
    quote_codes = _currency_codes(symbols, field="symbols")
    _iso_date(date, field="date")
    try:
        rows = await get_client().rates(base=base_code, quotes=quote_codes, date=date)
    except UpstreamError as exc:
        log.warning(
            "historical_rate(%s, %s, symbols=%s) failed: %s", date, base_code, quote_codes, exc
        )
        raise ToolError(f"exchange rate service unavailable: {exc}") from exc
    try:
        return to_rates_snapshot(rows, requested_date=date)
    except ValueError as exc:
        raise ToolError(
            f"no exchange rates available for base currency {base_code} on {date}"
        ) from exc


@mcp.tool()
async def rate_timeseries(
    start_date: Annotated[str, Field(description="First date of the range, as YYYY-MM-DD.")],
    end_date: Annotated[
        str,
        Field(
            description=f"Last date of the range, as YYYY-MM-DD. At most {MAX_RANGE_DAYS} days "
            "after start_date."
        ),
    ],
    base: Annotated[
        str, Field(description="Currency the rate is quoted against, as a 3-letter ISO 4217 code.")
    ] = "EUR",
    symbol: Annotated[
        str, Field(description="Currency to track across the range, as a 3-letter ISO 4217 code.")
    ] = "USD",
) -> RateTimeseries:
    """ECB reference rate for one currency pair across a date range.

    Returns one point per working day the ECB published a rate on, plus the minimum, maximum and
    average rate across the range. Refuses a range longer than the configured maximum, or one
    where `start_date` is after `end_date` — upstream is never called for either.
    """
    base_code = _currency_code(base, field="base")
    quote_code = _currency_code(symbol, field="symbol")
    start = _iso_date(start_date, field="start_date")
    end = _iso_date(end_date, field="end_date")
    if start > end:
        raise ToolError(
            f"start_date must not be after end_date, got start_date={start_date} "
            f"end_date={end_date}"
        )
    span_days = (end - start).days
    if span_days > MAX_RANGE_DAYS:
        raise ToolError(f"date range must not exceed {MAX_RANGE_DAYS} days, got {span_days} days")
    try:
        rows = await get_client().rates_range(
            date_from=start_date, date_to=end_date, base=base_code, quotes=[quote_code]
        )
    except UpstreamError as exc:
        log.warning(
            "rate_timeseries(%s, %s, %s, %s) failed: %s",
            start_date,
            end_date,
            base_code,
            quote_code,
            exc,
        )
        raise ToolError(f"exchange rate service unavailable: {exc}") from exc
    try:
        return to_rate_timeseries(rows)
    except ValueError as exc:
        raise ToolError(
            f"no exchange rate data for {quote_code} between {start_date} and {end_date}"
        ) from exc


@mcp.tool()
async def list_currencies() -> list[Currency]:
    """The ISO 4217 currencies Frankfurter tracks against the euro.

    Returns each currency's code and name, e.g. `{"code": "USD", "name": "United States
    Dollar"}`. Use it to check whether a currency code is valid before calling the other tools.
    """
    try:
        rows = await get_client().currencies()
    except UpstreamError as exc:
        log.warning("list_currencies() failed: %s", exc)
        raise ToolError(f"currency catalogue service unavailable: {exc}") from exc
    return to_currencies(rows)
