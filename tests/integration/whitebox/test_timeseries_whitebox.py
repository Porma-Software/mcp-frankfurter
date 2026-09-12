# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""FX-20..FX-27 by calling `rate_timeseries` directly, the upstream HTTP boundary mocked."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_frankfurter.server import MAX_RANGE_DAYS, rate_timeseries
from tests.integration.scenarios import scenario

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def range_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"{BASE_URL}/rates")


@scenario("FX-20")
async def test_rate_timeseries_happy_path(range_route: respx.Route) -> None:
    payload = _fixture("v2_rates_range_30d")
    assert isinstance(payload, list)
    rates = [item["rate"] for item in payload]
    range_route.mock(return_value=httpx.Response(200, json=payload))

    result = await rate_timeseries("2026-08-10", "2026-09-08", base="eur", symbol="usd")

    assert result["base"] == "EUR"
    assert result["quote"] == "USD"
    assert result["start_date"] == "2026-08-10"
    assert result["end_date"] == "2026-09-08"
    assert len(result["points"]) == 30
    assert result["points"][0] == {"date": "2026-08-10", "rate": 1.1553}
    assert result["points"][-1] == {"date": "2026-09-08", "rate": 1.1621}
    assert result["min"] == min(rates)
    assert result["max"] == max(rates)
    assert result["average"] == pytest.approx(sum(rates) / len(rates))
    sent = range_route.calls.last.request.url.params
    assert sent["from"] == "2026-08-10"
    assert sent["to"] == "2026-09-08"
    assert sent["quotes"] == "USD"


@scenario("FX-21")
async def test_rate_timeseries_defaults_base_and_symbol(range_route: respx.Route) -> None:
    range_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d")))

    await rate_timeseries("2026-08-10", "2026-09-08")

    sent = range_route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert sent["quotes"] == "USD"


@scenario("FX-22")
async def test_rate_timeseries_rejects_start_after_end(range_route: respx.Route) -> None:
    with pytest.raises(ToolError) as exc:
        await rate_timeseries("2026-09-08", "2026-09-01")
    assert str(exc.value) == (
        "start_date must not be after end_date, got start_date=2026-09-08 end_date=2026-09-01"
    )
    assert not range_route.called


@scenario("FX-23")
async def test_rate_timeseries_rejects_a_range_over_the_limit(range_route: respx.Route) -> None:
    # 2025-01-01..2026-01-03 spans 367 days, one more than MAX_RANGE_DAYS.
    with pytest.raises(ToolError) as exc:
        await rate_timeseries("2025-01-01", "2026-01-03")
    assert str(exc.value) == f"date range must not exceed {MAX_RANGE_DAYS} days, got 367 days"
    assert not range_route.called


@scenario("FX-24")
@pytest.mark.parametrize(
    ("start_date", "end_date", "message"),
    [
        (
            "2026/08/10",
            "2026-09-08",
            "start_date must be a date in YYYY-MM-DD format, got '2026/08/10'",
        ),
        ("2026-08-10", "2026-02-30", "end_date must be a valid calendar date, got '2026-02-30'"),
    ],
    ids=["bad-start-format", "bad-end-calendar"],
)
async def test_rate_timeseries_rejects_invalid_dates(
    range_route: respx.Route, start_date: str, end_date: str, message: str
) -> None:
    with pytest.raises(ToolError) as exc:
        await rate_timeseries(start_date, end_date)
    assert str(exc.value) == message
    assert not range_route.called


@scenario("FX-25")
async def test_rate_timeseries_rejects_invalid_symbol(range_route: respx.Route) -> None:
    with pytest.raises(ToolError) as exc:
        await rate_timeseries("2026-08-10", "2026-09-08", symbol="US")
    assert str(exc.value) == "symbol must be a 3-letter ISO 4217 currency code, got 'US'"
    assert not range_route.called


@scenario("FX-26")
async def test_rate_timeseries_reports_no_data(range_route: respx.Route) -> None:
    range_route.mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as exc:
        await rate_timeseries("2026-08-10", "2026-08-11")

    assert str(exc.value) == "no exchange rate data for USD between 2026-08-10 and 2026-08-11"


@scenario("FX-27")
async def test_rate_timeseries_upstream_error_is_a_tool_error(range_route: respx.Route) -> None:
    range_route.mock(return_value=httpx.Response(502, text="down"))

    with pytest.raises(ToolError) as exc:
        await rate_timeseries("2026-08-10", "2026-09-08")

    assert str(exc.value) == (
        f"exchange rate service unavailable: {BASE_URL}/rates returned HTTP 502: down"
    )
