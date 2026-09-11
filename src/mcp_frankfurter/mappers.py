# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Pure mapping functions and typed records at every boundary this server crosses.

Two boundaries, two directions:

- `parse_*` turns raw upstream JSON (the Frankfurter `v2` shapes probed in `docs/DECISIONS.md`)
  into frozen domain records (`RateRow`, `CurrencyRow`), raising `ValueError` on a malformed
  payload.
- `to_*` turns those records into the `TypedDict` DTOs a tool will return to the model
  (`RatesSnapshot`, `Conversion`, `RateTimeseries`, `Currency`), raising `ValueError` when the
  records cannot answer the request (e.g. no row for the requested quote currency).

`upstream.py`'s endpoint methods build `RateRow`/`CurrencyRow` lists through the `parse_*`
functions; `server.py`'s five tools call the `to_*` functions to shape their result. Both
directions are tested field by field here on plain data.

No `mcp` or `httpx` import here, so every function stays unit-testable on plain data, without a
mocked HTTP call or a running server.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypedDict

__all__ = [
    "CurrencyRow",
    "RateRow",
    "Currency",
    "Conversion",
    "RatePoint",
    "RateTimeseries",
    "RatesSnapshot",
    "parse_currency_rows",
    "parse_rate_rows",
    "to_conversion",
    "to_currencies",
    "to_rate_timeseries",
    "to_rates_snapshot",
]


# ---------------------------------------------------------------------------------------------
# Domain records: one row per `v2/rates` or `v2/currencies` JSON array item.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RateRow:
    """One `EUR -> quote` reference rate, as published by the ECB on `date`.

    `date` is the date the ECB actually published this rate, which is `v2`'s own per-currency
    granularity: two rows from the same response can carry different dates when one currency's
    feed lags another's (see the `v2_rates_historical_weekend` fixture in `docs/DECISIONS.md`'s
    probe, where `ANG` still carries the previous working day while `GBP`/`USD` already have the
    requested date).
    """

    date: str
    base: str
    quote: str
    rate: float


@dataclass(frozen=True, slots=True)
class CurrencyRow:
    """One entry of the `v2/currencies` catalogue."""

    iso_code: str
    iso_numeric: str
    name: str
    symbol: str
    start_date: str
    end_date: str


# ---------------------------------------------------------------------------------------------
# Tool DTOs: what a `@mcp.tool()` function will return to the model.
# ---------------------------------------------------------------------------------------------


class RatePoint(TypedDict):
    """One point of a `rate_timeseries` result."""

    date: str
    rate: float


class RatesSnapshot(TypedDict):
    """Shared shape for `latest_rates` and `historical_rate`: one or more quote currencies as of
    a single `rate_date`, with a plain-language `note` whenever that date needed explaining —
    either because it differs from what the caller asked for, or because one of the quote
    currencies in `rates` is older than `rate_date` (see `RateRow.date`).

    `requested_date` echoes the date the caller asked for: `None` for `latest_rates` (there is no
    specific date to echo), or the `historical_rate` date argument, which can differ from
    `rate_date` when the ECB had not published on that day (see `note`)."""

    base: str
    requested_date: str | None
    rate_date: str
    rates: dict[str, float]
    note: str | None


class Conversion(TypedDict):
    """`convert`'s result: `amount` of `from_currency` converted to `to_currency`."""

    amount: float
    from_currency: str
    to_currency: str
    rate: float
    converted: float
    rate_date: str
    note: str | None


class RateTimeseries(TypedDict):
    """`rate_timeseries`'s result: one quote currency across a date range."""

    base: str
    quote: str
    start_date: str
    end_date: str
    points: list[RatePoint]
    min: float
    max: float
    average: float


class Currency(TypedDict):
    """`list_currencies`'s result: the ISO 4217 code and name a business user recognises."""

    code: str
    name: str


# ---------------------------------------------------------------------------------------------
# parse_*: upstream JSON -> domain records.
# ---------------------------------------------------------------------------------------------


def _field(item: dict[str, object], key: str, *, label: str) -> object:
    if key not in item:
        raise ValueError(f"{label} is missing required field {key!r}: {item!r}")
    return item[key]


def _str_field(item: dict[str, object], key: str, *, label: str) -> str:
    value = _field(item, key, label=label)
    if not isinstance(value, str):
        raise ValueError(f"{label} field {key!r} must be a string, got {type(value).__name__}")
    return value


def _number_field(item: dict[str, object], key: str, *, label: str) -> float:
    value = _field(item, key, label=label)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} field {key!r} must be a number, got {type(value).__name__}")
    return float(value)


def parse_rate_rows(payload: object) -> list[RateRow]:
    """Parse a `v2/rates` response: a JSON array of `{date, base, quote, rate}` objects."""
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON array of rate rows, got {type(payload).__name__}")
    return [_parse_rate_row(item, index) for index, item in enumerate(payload)]


def _parse_rate_row(item: object, index: int) -> RateRow:
    label = f"rate row {index}"
    if not isinstance(item, dict):
        raise ValueError(f"{label} must be an object, got {type(item).__name__}")
    return RateRow(
        date=_str_field(item, "date", label=label),
        base=_str_field(item, "base", label=label),
        quote=_str_field(item, "quote", label=label),
        rate=_number_field(item, "rate", label=label),
    )


def parse_currency_rows(payload: object) -> list[CurrencyRow]:
    """Parse a `v2/currencies` response: a JSON array of currency-catalogue objects."""
    if not isinstance(payload, list):
        raise ValueError(f"expected a JSON array of currencies, got {type(payload).__name__}")
    return [_parse_currency_row(item, index) for index, item in enumerate(payload)]


def _parse_currency_row(item: object, index: int) -> CurrencyRow:
    label = f"currency row {index}"
    if not isinstance(item, dict):
        raise ValueError(f"{label} must be an object, got {type(item).__name__}")
    return CurrencyRow(
        iso_code=_str_field(item, "iso_code", label=label),
        iso_numeric=_str_field(item, "iso_numeric", label=label),
        name=_str_field(item, "name", label=label),
        symbol=_str_field(item, "symbol", label=label),
        start_date=_str_field(item, "start_date", label=label),
        end_date=_str_field(item, "end_date", label=label),
    )


# ---------------------------------------------------------------------------------------------
# to_*: domain records -> tool DTOs.
# ---------------------------------------------------------------------------------------------


def _date_note(*, requested_date: str | None, rate_date: str) -> str | None:
    if requested_date is not None and requested_date != rate_date:
        return (
            f"Requested {requested_date}, but the ECB publishes reference rates on working days "
            f"only; showing the most recent published rate, dated {rate_date}."
        )
    return None


def to_rates_snapshot(
    rows: Sequence[RateRow], *, requested_date: str | None = None
) -> RatesSnapshot:
    """Build a `RatesSnapshot` from one or more `RateRow`s sharing a `base` currency.

    `rate_date` is the most recent date among `rows`. `note` explains that date whenever it
    differs from `requested_date` (pass `None` for "latest", which never triggers this note by
    itself) and, separately, names any quote currency whose own row is older than `rate_date`.
    """
    if not rows:
        raise ValueError("no rates returned: rows is empty")
    base = rows[0].base
    rate_date = max(row.date for row in rows)
    rates = {row.quote: row.rate for row in rows}
    stale = sorted((row.quote, row.date) for row in rows if row.date != rate_date)

    notes: list[str] = []
    requested_note = _date_note(requested_date=requested_date, rate_date=rate_date)
    if requested_note is not None:
        notes.append(requested_note)
    if stale:
        listed = ", ".join(f"{quote} ({date})" for quote, date in stale)
        notes.append(f"Older data for {listed}: no more recent published rate available yet.")

    return RatesSnapshot(
        base=base,
        requested_date=requested_date,
        rate_date=rate_date,
        rates=rates,
        note=" ".join(notes) or None,
    )


def to_conversion(
    rows: Sequence[RateRow], *, amount: float, quote: str, requested_date: str | None = None
) -> Conversion:
    """Build a `Conversion` for `quote` out of `rows` (as returned by `UpstreamClient.rates`)."""
    row = next((candidate for candidate in rows if candidate.quote == quote), None)
    if row is None:
        raise ValueError(f"no rate returned for {quote!r}")
    return Conversion(
        amount=amount,
        from_currency=row.base,
        to_currency=row.quote,
        rate=row.rate,
        converted=amount * row.rate,
        rate_date=row.date,
        note=_date_note(requested_date=requested_date, rate_date=row.date),
    )


def to_rate_timeseries(rows: Sequence[RateRow]) -> RateTimeseries:
    """Build a `RateTimeseries` out of `rows` for a single quote currency across a date range."""
    if not rows:
        raise ValueError("no data points returned for this range")
    ordered = sorted(rows, key=lambda row: row.date)
    rates = [row.rate for row in ordered]
    return RateTimeseries(
        base=ordered[0].base,
        quote=ordered[0].quote,
        start_date=ordered[0].date,
        end_date=ordered[-1].date,
        points=[RatePoint(date=row.date, rate=row.rate) for row in ordered],
        min=min(rates),
        max=max(rates),
        average=sum(rates) / len(rates),
    )


def to_currencies(rows: Sequence[CurrencyRow]) -> list[Currency]:
    """Build the `list_currencies` DTO: just the ISO code and name a business user reads."""
    return [Currency(code=row.iso_code, name=row.name) for row in rows]
