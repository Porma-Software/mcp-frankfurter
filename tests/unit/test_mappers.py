# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""`mappers.py` field by field: `parse_*` on plain JSON-shaped data, `to_*` on plain records.

No mock, no network, no fixture file: every payload here is a small literal so each assertion
pins exactly the field or branch it targets, per the `mcp-testing` skill's "pin the outcome, not
the call" rule. `tests/integration/whitebox/test_upstream_whitebox.py` covers the same parsers
again, end to end, against the real fixtures in `tests/fixtures/`.
"""

import pytest

from mcp_frankfurter.mappers import (
    Currency,
    CurrencyRow,
    RatePoint,
    RateRow,
    parse_currency_rows,
    parse_rate_rows,
    to_conversion,
    to_currencies,
    to_rate_timeseries,
    to_rates_snapshot,
)

# ---------------------------------------------------------------------------------------------
# parse_rate_rows
# ---------------------------------------------------------------------------------------------


def test_parse_rate_rows_happy() -> None:
    payload = [
        {"date": "2026-09-11", "base": "EUR", "quote": "USD", "rate": 1.1627},
        {"date": "2026-09-11", "base": "EUR", "quote": "GBP", "rate": 0.85867},
    ]

    rows = parse_rate_rows(payload)

    assert rows == [
        RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627),
        RateRow(date="2026-09-11", base="EUR", quote="GBP", rate=0.85867),
    ]


def test_parse_rate_rows_accepts_an_integer_rate() -> None:
    # amount=1 base=quote pairs sometimes arrive as a bare 1, not 1.0.
    rows = parse_rate_rows([{"date": "2026-09-11", "base": "EUR", "quote": "EUR", "rate": 1}])

    assert rows == [RateRow(date="2026-09-11", base="EUR", quote="EUR", rate=1.0)]
    assert isinstance(rows[0].rate, float)


def test_parse_rate_rows_rejects_a_non_list_payload() -> None:
    with pytest.raises(ValueError) as exc:
        parse_rate_rows({"date": "2026-09-11"})

    assert str(exc.value) == "expected a JSON array of rate rows, got dict"


def test_parse_rate_rows_rejects_a_non_object_item() -> None:
    with pytest.raises(ValueError) as exc:
        parse_rate_rows(["not an object"])

    assert str(exc.value) == "rate row 0 must be an object, got str"


@pytest.mark.parametrize("missing_key", ["date", "base", "quote", "rate"])
def test_parse_rate_rows_rejects_a_missing_field(missing_key: str) -> None:
    item = {"date": "2026-09-11", "base": "EUR", "quote": "USD", "rate": 1.1627}
    del item[missing_key]

    with pytest.raises(ValueError) as exc:
        parse_rate_rows([item])

    assert str(exc.value) == f"rate row 0 is missing required field {missing_key!r}: {item!r}"


def test_parse_rate_rows_rejects_a_non_string_date() -> None:
    item = {"date": 20260911, "base": "EUR", "quote": "USD", "rate": 1.1627}

    with pytest.raises(ValueError) as exc:
        parse_rate_rows([item])

    assert str(exc.value) == "rate row 0 field 'date' must be a string, got int"


def test_parse_rate_rows_rejects_a_non_number_rate() -> None:
    item = {"date": "2026-09-11", "base": "EUR", "quote": "USD", "rate": "1.1627"}

    with pytest.raises(ValueError) as exc:
        parse_rate_rows([item])

    assert str(exc.value) == "rate row 0 field 'rate' must be a number, got str"


def test_parse_rate_rows_rejects_a_boolean_rate() -> None:
    # bool is a subclass of int in Python; it must not pass as a "number".
    item = {"date": "2026-09-11", "base": "EUR", "quote": "USD", "rate": True}

    with pytest.raises(ValueError) as exc:
        parse_rate_rows([item])

    assert str(exc.value) == "rate row 0 field 'rate' must be a number, got bool"


# ---------------------------------------------------------------------------------------------
# parse_currency_rows
# ---------------------------------------------------------------------------------------------

_CURRENCY_ITEM = {
    "iso_code": "USD",
    "iso_numeric": "840",
    "name": "United States Dollar",
    "symbol": "$",
    "start_date": "1792-01-01",
    "end_date": "2026-09-11",
}


def test_parse_currency_rows_happy() -> None:
    rows = parse_currency_rows([_CURRENCY_ITEM])

    assert rows == [
        CurrencyRow(
            iso_code="USD",
            iso_numeric="840",
            name="United States Dollar",
            symbol="$",
            start_date="1792-01-01",
            end_date="2026-09-11",
        )
    ]


def test_parse_currency_rows_rejects_a_non_list_payload() -> None:
    with pytest.raises(ValueError) as exc:
        parse_currency_rows(_CURRENCY_ITEM)

    assert str(exc.value) == "expected a JSON array of currencies, got dict"


def test_parse_currency_rows_rejects_a_non_object_item() -> None:
    with pytest.raises(ValueError) as exc:
        parse_currency_rows([123])

    assert str(exc.value) == "currency row 0 must be an object, got int"


@pytest.mark.parametrize(
    "missing_key", ["iso_code", "iso_numeric", "name", "symbol", "start_date", "end_date"]
)
def test_parse_currency_rows_rejects_a_missing_field(missing_key: str) -> None:
    item = dict(_CURRENCY_ITEM)
    del item[missing_key]

    with pytest.raises(ValueError) as exc:
        parse_currency_rows([item])

    assert str(exc.value) == f"currency row 0 is missing required field {missing_key!r}: {item!r}"


def test_parse_currency_rows_rejects_a_non_string_name() -> None:
    item = dict(_CURRENCY_ITEM, name=None)

    with pytest.raises(ValueError) as exc:
        parse_currency_rows([item])

    assert str(exc.value) == "currency row 0 field 'name' must be a string, got NoneType"


# ---------------------------------------------------------------------------------------------
# to_rates_snapshot
# ---------------------------------------------------------------------------------------------


def test_to_rates_snapshot_rejects_empty_rows() -> None:
    with pytest.raises(ValueError) as exc:
        to_rates_snapshot([])

    assert str(exc.value) == "no rates returned: rows is empty"


def test_to_rates_snapshot_with_no_requested_date_and_a_single_shared_date() -> None:
    rows = [
        RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627),
        RateRow(date="2026-09-11", base="EUR", quote="GBP", rate=0.85867),
    ]

    snapshot = to_rates_snapshot(rows)

    assert snapshot == {
        "base": "EUR",
        "requested_date": None,
        "rate_date": "2026-09-11",
        "rates": {"USD": 1.1627, "GBP": 0.85867},
        "note": None,
    }


def test_to_rates_snapshot_notes_a_requested_date_that_differs_from_rate_date() -> None:
    rows = [RateRow(date="2026-09-04", base="EUR", quote="USD", rate=1.1625)]

    snapshot = to_rates_snapshot(rows, requested_date="2026-09-06")

    assert snapshot["requested_date"] == "2026-09-06"
    assert snapshot["rate_date"] == "2026-09-04"
    assert snapshot["note"] == (
        "Requested 2026-09-06, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


def test_to_rates_snapshot_matching_requested_date_has_no_note() -> None:
    rows = [RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627)]

    snapshot = to_rates_snapshot(rows, requested_date="2026-09-11")

    assert snapshot["requested_date"] == "2026-09-11"
    assert snapshot["note"] is None


def test_to_rates_snapshot_notes_a_stale_quote_currency() -> None:
    # The real ANG-vs-GBP/USD case from the v2_rates_historical_weekend fixture.
    rows = [
        RateRow(date="2026-09-04", base="EUR", quote="ANG", rate=2.0813),
        RateRow(date="2026-09-06", base="EUR", quote="GBP", rate=0.85901),
        RateRow(date="2026-09-06", base="EUR", quote="USD", rate=1.1627),
    ]

    snapshot = to_rates_snapshot(rows, requested_date="2026-09-06")

    assert snapshot["rate_date"] == "2026-09-06"
    assert snapshot["rates"] == {"ANG": 2.0813, "GBP": 0.85901, "USD": 1.1627}
    assert snapshot["note"] == (
        "Older data for ANG (2026-09-04): no more recent published rate available yet."
    )


def test_to_rates_snapshot_notes_multiple_stale_quote_currencies() -> None:
    # Two lagging currencies: pins the ", " separator joining the listed entries, not just
    # whether one of them appears.
    rows = [
        RateRow(date="2026-09-04", base="EUR", quote="ANG", rate=2.0813),
        RateRow(date="2026-09-05", base="EUR", quote="JPY", rate=179.0),
        RateRow(date="2026-09-06", base="EUR", quote="USD", rate=1.1627),
    ]

    snapshot = to_rates_snapshot(rows, requested_date="2026-09-06")

    assert snapshot["note"] == (
        "Older data for ANG (2026-09-04), JPY (2026-09-05): no more recent published rate "
        "available yet."
    )


def test_to_rates_snapshot_combines_both_notes_when_both_apply() -> None:
    rows = [
        RateRow(date="2026-09-04", base="EUR", quote="ANG", rate=2.0813),
        RateRow(date="2026-09-06", base="EUR", quote="USD", rate=1.1627),
    ]

    snapshot = to_rates_snapshot(rows, requested_date="2026-09-07")

    assert snapshot["note"] == (
        "Requested 2026-09-07, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-06. "
        "Older data for ANG (2026-09-04): no more recent published rate available yet."
    )


# ---------------------------------------------------------------------------------------------
# to_conversion
# ---------------------------------------------------------------------------------------------


def test_to_conversion_happy_path() -> None:
    rows = [RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627)]

    conversion = to_conversion(rows, amount=10.0, quote="USD")

    assert conversion == {
        "amount": 10.0,
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate": 1.1627,
        "converted": 11.627,
        "rate_date": "2026-09-11",
        "note": None,
    }


def test_to_conversion_notes_a_requested_date_mismatch() -> None:
    rows = [RateRow(date="2026-09-04", base="EUR", quote="USD", rate=1.1625)]

    conversion = to_conversion(rows, amount=1.0, quote="USD", requested_date="2026-09-06")

    assert conversion["rate_date"] == "2026-09-04"
    assert conversion["note"] == (
        "Requested 2026-09-06, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


def test_to_conversion_rejects_a_quote_currency_not_in_rows() -> None:
    rows = [RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627)]

    with pytest.raises(ValueError) as exc:
        to_conversion(rows, amount=1.0, quote="JPY")

    assert str(exc.value) == "no rate returned for 'JPY'"


# ---------------------------------------------------------------------------------------------
# to_rate_timeseries
# ---------------------------------------------------------------------------------------------


def test_to_rate_timeseries_rejects_empty_rows() -> None:
    with pytest.raises(ValueError) as exc:
        to_rate_timeseries([])

    assert str(exc.value) == "no data points returned for this range"


def test_to_rate_timeseries_sorts_and_summarises_out_of_order_rows() -> None:
    rows = [
        RateRow(date="2026-08-12", base="EUR", quote="USD", rate=1.1541),
        RateRow(date="2026-08-10", base="EUR", quote="USD", rate=1.1553),
        RateRow(date="2026-08-11", base="EUR", quote="USD", rate=1.1503),
    ]

    series = to_rate_timeseries(rows)

    assert series == {
        "base": "EUR",
        "quote": "USD",
        "start_date": "2026-08-10",
        "end_date": "2026-08-12",
        "points": [
            {"date": "2026-08-10", "rate": 1.1553},
            {"date": "2026-08-11", "rate": 1.1503},
            {"date": "2026-08-12", "rate": 1.1541},
        ],
        "min": 1.1503,
        "max": 1.1553,
        "average": pytest.approx((1.1553 + 1.1503 + 1.1541) / 3),
    }


def test_to_rate_timeseries_with_a_single_point() -> None:
    rows = [RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627)]

    series = to_rate_timeseries(rows)

    assert series["min"] == series["max"] == series["average"] == 1.1627
    assert series["points"] == [RatePoint(date="2026-09-11", rate=1.1627)]


# ---------------------------------------------------------------------------------------------
# to_currencies
# ---------------------------------------------------------------------------------------------


def test_to_currencies_keeps_only_code_and_name() -> None:
    rows = [
        CurrencyRow(
            iso_code="USD",
            iso_numeric="840",
            name="United States Dollar",
            symbol="$",
            start_date="1792-01-01",
            end_date="2026-09-11",
        )
    ]

    assert to_currencies(rows) == [Currency(code="USD", name="United States Dollar")]


def test_to_currencies_on_an_empty_list() -> None:
    assert to_currencies([]) == []
