# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""FX-01..FX-08 by calling `convert` directly, the upstream HTTP boundary mocked.

White-box: same shape as test_upstream_whitebox.py. Every `pytest.raises` pins the exact
message: a substring match still matches mutmut's mutated `"XX<literal>XX"` string, so it proves
nothing about that literal.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_frankfurter.server import convert
from tests.integration.scenarios import scenario

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def rates_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"{BASE_URL}/rates")


# AUTH-05 is tagged here: docs/scenarios.md points at a tool test as the white-box shape of "no
# bearer layer at all" -- every white-box test calls the tool function directly, with no
# BearerTokenMiddleware in front, which *is* what a stdio session looks like in-process.
@scenario("FX-01", "AUTH-05")
async def test_convert_latest_rate(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rate_pair_latest")))

    result = await convert(10.0, "eur", "usd")

    assert result == {
        "amount": 10.0,
        "from_currency": "EUR",
        "to_currency": "USD",
        "rate": 1.1627,
        "converted": 11.627,
        "rate_date": "2026-09-11",
        "note": None,
    }
    sent = rates_route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert sent["quotes"] == "USD"
    assert "date" not in sent


@scenario("FX-02")
async def test_convert_on_a_working_day(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekday")))

    result = await convert(5.0, "EUR", "USD", date="2026-09-08")

    assert result["rate"] == 1.1621
    assert result["rate_date"] == "2026-09-08"
    assert result["converted"] == pytest.approx(5.0 * 1.1621)
    assert result["note"] is None
    assert rates_route.calls.last.request.url.params["date"] == "2026-09-08"


@scenario("FX-03")
async def test_convert_on_a_weekend_rolls_back(rates_route: respx.Route) -> None:
    # ANG's own feed lags on this date, the real quirk documented in docs/DECISIONS.md.
    rates_route.mock(
        return_value=httpx.Response(
            200, json=[{"date": "2026-09-04", "base": "EUR", "quote": "ANG", "rate": 2.0813}]
        )
    )

    result = await convert(1.0, "EUR", "ANG", date="2026-09-06")

    assert result["rate_date"] == "2026-09-04"
    assert result["note"] == (
        "Requested 2026-09-06, but the ECB publishes reference rates on working days only; "
        "showing the most recent published rate, dated 2026-09-04."
    )


@scenario("FX-04")
@pytest.mark.parametrize(
    ("from_currency", "to_currency", "message"),
    [
        ("EU", "USD", "from_currency must be a 3-letter ISO 4217 currency code, got 'EU'"),
        ("EUR", "US1", "to_currency must be a 3-letter ISO 4217 currency code, got 'US1'"),
        ("", "USD", "from_currency must be a 3-letter ISO 4217 currency code, got ''"),
    ],
    ids=["from-too-short", "to-has-digit", "from-empty"],
)
async def test_convert_rejects_invalid_currency_codes(
    rates_route: respx.Route, from_currency: str, to_currency: str, message: str
) -> None:
    with pytest.raises(ToolError) as exc:
        await convert(1.0, from_currency, to_currency)
    assert str(exc.value) == message
    assert not rates_route.called


@scenario("FX-05")
@pytest.mark.parametrize("amount", [0, -5.0])
async def test_convert_rejects_non_positive_amount(rates_route: respx.Route, amount: float) -> None:
    with pytest.raises(ToolError) as exc:
        await convert(amount, "EUR", "USD")
    assert str(exc.value) == f"amount must be positive, got {amount}"
    assert not rates_route.called


@scenario("FX-06")
@pytest.mark.parametrize(
    ("date", "message"),
    [
        ("2026-9-8", "date must be a date in YYYY-MM-DD format, got '2026-9-8'"),
        ("not-a-date", "date must be a date in YYYY-MM-DD format, got 'not-a-date'"),
        ("2026-13-01", "date must be a valid calendar date, got '2026-13-01'"),
    ],
    ids=["missing-zero-pad", "not-a-date", "invalid-month"],
)
async def test_convert_rejects_invalid_date(
    rates_route: respx.Route, date: str, message: str
) -> None:
    with pytest.raises(ToolError) as exc:
        await convert(1.0, "EUR", "USD", date=date)
    assert str(exc.value) == message
    assert not rates_route.called


@scenario("FX-07")
async def test_convert_reports_no_data_for_the_date(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(200, json=[]))

    with pytest.raises(ToolError) as exc:
        await convert(1.0, "EUR", "USD", date="1990-01-01")

    assert str(exc.value) == (
        "no exchange rate available from EUR to USD on 1990-01-01: the ECB may not track this "
        "currency, or has not published a rate for that date"
    )


@scenario("FX-08")
async def test_convert_upstream_error_is_a_tool_error(rates_route: respx.Route) -> None:
    rates_route.mock(return_value=httpx.Response(503, text="down"))

    with pytest.raises(ToolError) as exc:
        await convert(1.0, "EUR", "USD")

    assert str(exc.value) == (
        f"exchange rate service unavailable: {BASE_URL}/rates returned HTTP 503"
    )
