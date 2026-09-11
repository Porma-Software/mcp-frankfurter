# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""SRV-01, FX-01..FX-29 and AUTH-05 through a real MCP client session.

Black-box: only `mcp.client.Client` is used, never a tool function or `UpstreamClient` directly.
`mode="legacy"` runs the server behind in-memory streams with JSON-RPC framing and the initialize
handshake — exactly what a stdio or HTTP client does. The default "auto" mode dispatches
in-process without serialising anything, which would hide schema regressions, so it is never used
here. The upstream HTTP call is mocked with `respx`: there is no real Frankfurter API available
in CI (see docs/scenarios.md "Scope"); `tests/test_live.py` is the canary that keeps that mock
honest.
"""

import json
from pathlib import Path

import httpx
import respx
from mcp.client import Client
from mcp.types import CallToolResult, TextContent

from mcp_frankfurter.server import SERVER_NAME, mcp
from tests.integration.scenarios import scenario

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"
TOOL_NAMES = {"convert", "latest_rates", "historical_rate", "rate_timeseries", "list_currencies"}


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def connect() -> Client:
    return Client(mcp, mode="legacy")


def text_of(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


@scenario("SRV-01")
async def test_lists_exactly_the_five_documented_tools() -> None:
    async with connect() as client:
        assert client.server_info is not None
        assert client.server_info.name == SERVER_NAME
        listed = await client.list_tools()

    assert {tool.name for tool in listed.tools} == TOOL_NAMES


# --- convert -------------------------------------------------------------------------------


# AUTH-05 is tagged here: an in-memory `mode="legacy"` session is the stdio shape — no HTTP, no
# bearer token — and this is the canonical happy path through it.
@scenario("FX-01", "AUTH-05")
async def test_convert_latest_rate(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rate_pair_latest"))
    )

    async with connect() as client:
        result = await client.call_tool(
            "convert", {"amount": 10.0, "from_currency": "eur", "to_currency": "usd"}
        )

    assert result.is_error is False
    assert result.structured_content == {
        "amount": 10.0,
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate": 1.1627,
        "converted": 11.627,
        "rate_date": "2026-09-11",
        "note": None,
    }


@scenario("FX-02")
async def test_convert_on_a_working_day(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekday"))
    )

    async with connect() as client:
        result = await client.call_tool(
            "convert",
            {"amount": 5.0, "from_currency": "EUR", "to_currency": "USD", "date": "2026-09-08"},
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["rate_date"] == "2026-09-08"
    assert result.structured_content["note"] is None


@scenario("FX-03")
async def test_convert_on_a_weekend_rolls_back(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(
            200, json=[{"date": "2026-09-04", "base": "EUR", "quote": "ANG", "rate": 2.0813}]
        )
    )

    async with connect() as client:
        result = await client.call_tool(
            "convert",
            {"amount": 1.0, "from_currency": "EUR", "to_currency": "ANG", "date": "2026-09-06"},
        )

    assert result.structured_content is not None
    assert result.structured_content["rate_date"] == "2026-09-04"
    assert result.structured_content["note"] == (
        "Requested 2026-09-06, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


@scenario("FX-04")
async def test_convert_rejects_invalid_currency_code(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "convert", {"amount": 1.0, "from_currency": "EU", "to_currency": "USD"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool convert: from_currency must be a 3-letter ISO 4217 currency "
        "code, got 'EU'"
    )
    assert not route.called


@scenario("FX-05")
async def test_convert_rejects_non_positive_amount(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "convert", {"amount": 0, "from_currency": "EUR", "to_currency": "USD"}
        )

    assert result.is_error is True
    assert text_of(result) == "Error executing tool convert: amount must be positive, got 0.0"
    assert not route.called


@scenario("FX-06")
async def test_convert_rejects_invalid_date(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "convert",
            {"amount": 1.0, "from_currency": "EUR", "to_currency": "USD", "date": "not-a-date"},
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool convert: date must be a date in YYYY-MM-DD format, got 'not-a-date'"
    )
    assert not route.called


@scenario("FX-07")
async def test_convert_reports_no_data(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json=[]))

    async with connect() as client:
        result = await client.call_tool(
            "convert",
            {"amount": 1.0, "from_currency": "EUR", "to_currency": "USD", "date": "1990-01-01"},
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool convert: no exchange rate available from EUR to USD on "
        "1990-01-01: the ECB may not track this currency, or has not published a rate for "
        "that date"
    )


@scenario("FX-08")
async def test_convert_upstream_error_is_an_error_result(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(503, text="down"))

    async with connect() as client:
        result = await client.call_tool(
            "convert", {"amount": 1.0, "from_currency": "EUR", "to_currency": "USD"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool convert: exchange rate service unavailable: "
        f"{BASE_URL}/rates returned HTTP 503"
    )


# --- latest_rates ----------------------------------------------------------------------------


@scenario("FX-09")
async def test_latest_rates_default(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_latest"))
    )

    async with connect() as client:
        result = await client.call_tool("latest_rates", {})

    assert result.is_error is False
    assert result.structured_content == {
        "base": "EUR",
        "requested_date": None,
        "rate_date": "2026-09-11",
        "rates": {"GBP": 0.85867, "JPY": 179.18, "USD": 1.1627},
        "note": None,
    }


@scenario("FX-10")
async def test_latest_rates_restricted_symbols(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_latest"))
    )

    async with connect() as client:
        result = await client.call_tool("latest_rates", {"symbols": ["gbp", "usd"]})

    assert result.is_error is False
    assert route.calls.last.request.url.params["quotes"] == "GBP,USD"


@scenario("FX-11")
async def test_latest_rates_rejects_invalid_base(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool("latest_rates", {"base": "EU"})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool latest_rates: base must be a 3-letter ISO 4217 currency code, "
        "got 'EU'"
    )
    assert not route.called


@scenario("FX-12")
async def test_latest_rates_upstream_error_is_an_error_result(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(503, text="down"))

    async with connect() as client:
        result = await client.call_tool("latest_rates", {})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool latest_rates: exchange rate service unavailable: "
        f"{BASE_URL}/rates returned HTTP 503"
    )


@scenario("FX-30")
async def test_latest_rates_reports_no_data(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json=[]))

    async with connect() as client:
        result = await client.call_tool("latest_rates", {"base": "XAU"})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool latest_rates: no exchange rates available for base currency XAU"
    )


# --- historical_rate -------------------------------------------------------------------------


@scenario("FX-13")
async def test_historical_rate_on_a_working_day(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekday"))
    )

    async with connect() as client:
        result = await client.call_tool("historical_rate", {"date": "2026-09-08"})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["requested_date"] == "2026-09-08"
    assert result.structured_content["rate_date"] == "2026-09-08"
    assert result.structured_content["note"] is None


@scenario("FX-14")
async def test_historical_rate_on_a_weekend_rolls_back(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"date": "2026-09-04", "base": "EUR", "quote": "GBP", "rate": 0.85901},
                {"date": "2026-09-04", "base": "EUR", "quote": "USD", "rate": 1.1625},
            ],
        )
    )

    async with connect() as client:
        result = await client.call_tool(
            "historical_rate", {"date": "2026-09-05", "symbols": ["GBP", "USD"]}
        )

    assert result.structured_content is not None
    assert result.structured_content["rate_date"] == "2026-09-04"
    assert result.structured_content["note"] == (
        "Requested 2026-09-05, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


@scenario("FX-15")
async def test_historical_rate_notes_a_per_currency_stale_rate(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekend"))
    )

    async with connect() as client:
        result = await client.call_tool(
            "historical_rate", {"date": "2026-09-06", "symbols": ["ANG", "GBP", "USD"]}
        )

    assert result.structured_content is not None
    assert result.structured_content["note"] == (
        "Older data for ANG (2026-09-04): no more recent published rate available yet."
    )


@scenario("FX-16")
async def test_historical_rate_rejects_invalid_date(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool("historical_rate", {"date": "2026-13-01"})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool historical_rate: date must be a valid calendar date, got '2026-13-01'"
    )
    assert not route.called


@scenario("FX-17")
async def test_historical_rate_rejects_invalid_symbol(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "historical_rate", {"date": "2026-09-08", "symbols": ["US1"]}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool historical_rate: symbols must be a 3-letter ISO 4217 currency "
        "code, got 'US1'"
    )
    assert not route.called


@scenario("FX-18")
async def test_historical_rate_reports_no_data(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json=[]))

    async with connect() as client:
        result = await client.call_tool("historical_rate", {"date": "1990-01-01"})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool historical_rate: no exchange rates available for base currency "
        "EUR on 1990-01-01"
    )


@scenario("FX-19")
async def test_historical_rate_upstream_error_is_an_error_result(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(500, text="down"))

    async with connect() as client:
        result = await client.call_tool("historical_rate", {"date": "2026-09-08"})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool historical_rate: exchange rate service unavailable: "
        f"{BASE_URL}/rates returned HTTP 500"
    )


# --- rate_timeseries -------------------------------------------------------------------------


@scenario("FX-20")
async def test_rate_timeseries_happy_path(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d"))
    )

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2026-08-10", "end_date": "2026-09-08"}
        )

    assert result.is_error is False
    assert result.structured_content is not None
    assert len(result.structured_content["points"]) == 30
    assert result.structured_content["base"] == "EUR"
    assert result.structured_content["quote"] == "USD"


@scenario("FX-21")
async def test_rate_timeseries_defaults(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d"))
    )

    async with connect() as client:
        await client.call_tool(
            "rate_timeseries", {"start_date": "2026-08-10", "end_date": "2026-09-08"}
        )

    sent = route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert sent["quotes"] == "USD"


@scenario("FX-22")
async def test_rate_timeseries_rejects_start_after_end(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2026-09-08", "end_date": "2026-09-01"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: start_date must not be after end_date, got "
        "start_date=2026-09-08 end_date=2026-09-01"
    )
    assert not route.called


@scenario("FX-23")
async def test_rate_timeseries_rejects_a_range_over_the_limit(
    respx_mock: respx.MockRouter,
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2025-01-01", "end_date": "2026-01-03"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: date range must not exceed 366 days, got 367 days"
    )
    assert not route.called


@scenario("FX-24")
async def test_rate_timeseries_rejects_invalid_dates(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2026/08/10", "end_date": "2026-09-08"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: start_date must be a date in YYYY-MM-DD format, "
        "got '2026/08/10'"
    )
    assert not route.called


@scenario("FX-25")
async def test_rate_timeseries_rejects_invalid_symbol(respx_mock: respx.MockRouter) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates")

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries",
            {"start_date": "2026-08-10", "end_date": "2026-09-08", "symbol": "US"},
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: symbol must be a 3-letter ISO 4217 currency "
        "code, got 'US'"
    )
    assert not route.called


@scenario("FX-26")
async def test_rate_timeseries_reports_no_data(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json=[]))

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2026-08-10", "end_date": "2026-08-11"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: no exchange rate data for USD between "
        "2026-08-10 and 2026-08-11"
    )


@scenario("FX-27")
async def test_rate_timeseries_upstream_error_is_an_error_result(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(502, text="down"))

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries", {"start_date": "2026-08-10", "end_date": "2026-09-08"}
        )

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool rate_timeseries: exchange rate service unavailable: "
        f"{BASE_URL}/rates returned HTTP 502"
    )


# --- list_currencies -------------------------------------------------------------------------


@scenario("FX-28")
async def test_list_currencies_happy_path(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"{BASE_URL}/currencies").mock(
        return_value=httpx.Response(200, json=_fixture("v2_currencies"))
    )

    async with connect() as client:
        result = await client.call_tool("list_currencies", {})

    assert result.is_error is False
    assert result.structured_content is not None
    currencies = result.structured_content["result"]
    assert len(currencies) == 165
    assert {"code": "EUR", "name": "Euro"} in currencies


@scenario("FX-29")
async def test_list_currencies_upstream_error_is_an_error_result(
    respx_mock: respx.MockRouter,
) -> None:
    respx_mock.get(f"{BASE_URL}/currencies").mock(return_value=httpx.Response(500, text="down"))

    async with connect() as client:
        result = await client.call_tool("list_currencies", {})

    assert result.is_error is True
    assert text_of(result) == (
        "Error executing tool list_currencies: currency catalogue service unavailable: "
        f"{BASE_URL}/currencies returned HTTP 500"
    )


async def test_an_unknown_tool_name_is_an_error_result(respx_mock: respx.MockRouter) -> None:
    # Not a catalogue scenario (there is no user action that names a tool): a protocol-level
    # safety net, kept next to the scenario-tagged tests it shares fixtures and helpers with.
    async with connect() as client:
        result = await client.call_tool("no_such_tool", {})

    assert result.is_error is True
