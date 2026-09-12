# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""FX-09..FX-19 by calling `latest_rates` and `historical_rate` directly, the upstream HTTP
boundary mocked. Every `pytest.raises` pins the exact message (see the mcp-testing skill).
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_frankfurter.server import historical_rate, latest_rates
from tests.integration.scenarios import scenario

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def rates_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"{BASE_URL}/rates")


# --- latest_rates --------------------------------------------------------------------------


@scenario("FX-09")
async def test_latest_rates_default_base_and_no_symbols(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_latest")))

    result = await latest_rates()

    assert result == {
        "base": "EUR",
        "requested_date": None,
        "rate_date": "2026-09-11",
        "rates": {"GBP": 0.85867, "JPY": 179.18, "USD": 1.1627},
        "note": None,
    }
    sent = rates_route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert "quotes" not in sent
    assert "date" not in sent


@scenario("FX-10")
async def test_latest_rates_restricted_symbols(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_latest")))

    await latest_rates(base="eur", symbols=["gbp", "usd"])

    assert rates_route.calls.last.request.url.params["quotes"] == "GBP,USD"


@scenario("FX-11")
@pytest.mark.parametrize(
    ("base", "symbols", "message"),
    [
        ("EU", None, "base must be a 3-letter ISO 4217 currency code, got 'EU'"),
        ("EUR", ["US1"], "symbols must be a 3-letter ISO 4217 currency code, got 'US1'"),
        ("EUR", [], "symbols must not be an empty list; omit it to include every currency"),
    ],
    ids=["bad-base", "bad-symbol", "empty-symbols"],
)
async def test_latest_rates_rejects_invalid_currency_codes(
    rates_route: respx.Route, base: str, symbols: list[str] | None, message: str
) -> None:
    with pytest.raises(ToolError) as exc:
        await latest_rates(base=base, symbols=symbols)
    assert str(exc.value) == message
    assert not rates_route.called


@scenario("FX-12")
async def test_latest_rates_upstream_error_is_a_tool_error(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(503, text="down"))

    with pytest.raises(ToolError) as exc:
        await latest_rates()

    assert str(exc.value) == (
        f"exchange rate service unavailable: {BASE_URL}/rates returned HTTP 503: down"
    )


@scenario("FX-30")
async def test_latest_rates_reports_no_data(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as exc:
        await latest_rates(base="XAU")

    assert str(exc.value) == "no exchange rates available for base currency XAU"


# --- historical_rate -------------------------------------------------------------------------


@scenario("FX-13")
async def test_historical_rate_on_a_working_day(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekday")))

    result = await historical_rate("2026-09-08")

    assert result["requested_date"] == "2026-09-08"
    assert result["rate_date"] == "2026-09-08"
    assert result["rates"] == {"GBP": 0.85862, "JPY": 179.41, "USD": 1.1621}
    assert result["note"] is None
    assert rates_route.calls.last.request.url.params["date"] == "2026-09-08"


@scenario("FX-14")
async def test_historical_rate_on_a_weekend_rolls_back(rates_route: respx.Route) -> None:
    # 2026-09-05 is a Saturday; every currency's own feed still carries Friday's date.
    rates_route.mock(
        return_value=httpx.Response(
            200,
            json=[
                {"date": "2026-09-04", "base": "EUR", "quote": "GBP", "rate": 0.85901},
                {"date": "2026-09-04", "base": "EUR", "quote": "USD", "rate": 1.1625},
            ],
        )
    )

    result = await historical_rate("2026-09-05", symbols=["GBP", "USD"])

    assert result["requested_date"] == "2026-09-05"
    assert result["rate_date"] == "2026-09-04"
    assert result["note"] == (
        "Requested 2026-09-05, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


@scenario("FX-15")
async def test_historical_rate_notes_a_per_currency_stale_rate(rates_route: respx.Route) -> None:
    # v2's own quirk (docs/DECISIONS.md): ANG's own feed still lags GBP/USD on this date.
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekend")))

    result = await historical_rate("2026-09-06", symbols=["ANG", "GBP", "USD"])

    assert result["requested_date"] == "2026-09-06"
    assert result["rate_date"] == "2026-09-06"
    assert result["rates"] == {"ANG": 2.0813, "GBP": 0.85901, "USD": 1.1627}
    assert result["note"] == (
        "Older data for ANG (2026-09-04): no more recent published rate available yet."
    )


@scenario("FX-16")
@pytest.mark.parametrize(
    ("date", "message"),
    [
        ("06-09-2026", "date must be a date in YYYY-MM-DD format, got '06-09-2026'"),
        ("2026-02-30", "date must be a valid calendar date, got '2026-02-30'"),
    ],
    ids=["wrong-order", "invalid-day"],
)
async def test_historical_rate_rejects_invalid_date(
    rates_route: respx.Route, date: str, message: str
) -> None:
    with pytest.raises(ToolError) as exc:
        await historical_rate(date)
    assert str(exc.value) == message
    assert not rates_route.called


@scenario("FX-17")
async def test_historical_rate_rejects_invalid_base(rates_route: respx.Route) -> None:
    with pytest.raises(ToolError) as exc:
        await historical_rate("2026-09-08", base="EURO")
    assert str(exc.value) == "base must be a 3-letter ISO 4217 currency code, got 'EURO'"
    assert not rates_route.called


@scenario("FX-18")
async def test_historical_rate_reports_no_data(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as exc:
        await historical_rate("1990-01-01")

    assert str(exc.value) == "no exchange rates available for base currency EUR on 1990-01-01"


@scenario("FX-19")
async def test_historical_rate_upstream_error_is_a_tool_error(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(500, text="down"))

    with pytest.raises(ToolError) as exc:
        await historical_rate("2026-09-08")

    assert str(exc.value) == (
        f"exchange rate service unavailable: {BASE_URL}/rates returned HTTP 500: down"
    )
