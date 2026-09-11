# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""The outbound adapter: generic wiring, plus the three `v2` endpoint methods against the real
captures in `tests/fixtures/` (see `docs/DECISIONS.md` for how each was probed).

White-box, untagged: no user scenario attaches to the client on its own (no tool calls it yet —
see `docs/scenarios.md`). Proves the request this client sends and the record list it returns,
and every way `UpstreamError` gets raised: HTTP status, network failure, a non-JSON body and a
JSON body of the wrong shape.
"""

import json
from pathlib import Path

import httpx
import pytest
import respx

from mcp_frankfurter.config import Settings
from mcp_frankfurter.mappers import CurrencyRow, RateRow
from mcp_frankfurter.upstream import USER_AGENT, UpstreamClient, UpstreamError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
async def client() -> UpstreamClient:
    async with UpstreamClient(base_url=BASE_URL) as instance:
        yield instance


# ---------------------------------------------------------------------------------------------
# Generic wiring
# ---------------------------------------------------------------------------------------------


async def test_base_url_strips_a_trailing_slash() -> None:
    # A real base URL usually arrives with one; rstrip("/") must not eat into the scheme.
    async with UpstreamClient(base_url="https://api.frankfurter.dev/v2/") as instance:
        assert instance.base_url == "https://api.frankfurter.dev/v2"


async def test_base_url_rstrip_removes_only_the_trailing_slash() -> None:
    # rstrip("/") strips exactly the trailing "/" character, not every trailing character that
    # happens to share a mutated character set with it (pins against a widened rstrip() charset).
    async with UpstreamClient(base_url="https://x.test/v2X/") as instance:
        assert instance.base_url == "https://x.test/v2X"


def test_timeout_seconds_is_stored() -> None:
    assert UpstreamClient(base_url="https://x.test", timeout_seconds=2.5).timeout_seconds == 2.5


def test_default_timeout_is_ten_seconds() -> None:
    assert UpstreamClient(base_url="https://x.test").timeout_seconds == 10.0


def test_user_agent_is_set_on_the_http_client() -> None:
    instance = UpstreamClient(base_url="https://x.test")

    assert instance._client.headers["User-Agent"] == USER_AGENT


def test_headers_carry_the_exact_documented_name_and_value() -> None:
    # httpx.Headers lookups are case-insensitive, so a plain instance._client.headers["Accept"]
    # cannot tell "Accept" from "accept"/"ACCEPT"/an unrelated key; .raw preserves the exact
    # bytes actually sent.
    instance = UpstreamClient(base_url="https://x.test")

    raw = dict(instance._client.headers.raw)

    assert raw[b"User-Agent"] == USER_AGENT.encode()
    assert raw[b"Accept"] == b"application/json"


def test_timeout_and_transport_reach_the_underlying_http_client() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[]))

    instance = UpstreamClient(base_url="https://x.test", timeout_seconds=7.0, transport=transport)

    assert instance._client._transport is transport
    assert instance._client.timeout == httpx.Timeout(7.0)


async def test_from_settings_wires_base_url_and_timeout() -> None:
    settings = Settings(
        _env_file=None,
        upstream_base_url="https://upstream.example.test/",
        http_timeout_seconds=3.5,
    )

    async with UpstreamClient.from_settings(settings) as instance:
        assert instance.base_url == "https://upstream.example.test"
        assert instance.timeout_seconds == 3.5


async def test_aclose_closes_the_underlying_http_client() -> None:
    instance = UpstreamClient(base_url="https://x.test")

    await instance.aclose()

    assert instance._client.is_closed is True


async def test_aclose_is_safe_to_call_twice() -> None:
    # httpx.AsyncClient.aclose() already tolerates a second call; this pins that UpstreamClient
    # does not add a guard of its own that would break on it.
    instance = UpstreamClient(base_url="https://x.test")
    await instance.aclose()

    await instance.aclose()


def test_upstream_error_carries_a_message_and_an_optional_status_code() -> None:
    bare = UpstreamError("boom")
    assert str(bare) == "boom"
    assert bare.status_code is None

    with_status = UpstreamError("boom", status_code=503)
    assert with_status.status_code == 503


# ---------------------------------------------------------------------------------------------
# rates() — latest (no date) and one historical date share the same endpoint and shape.
# ---------------------------------------------------------------------------------------------


async def test_rates_latest_parses_the_fixture(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_latest"))
    )

    rows = await client.rates(base="EUR", quotes=["GBP", "JPY", "USD"])

    assert rows == [
        RateRow(date="2026-09-11", base="EUR", quote="GBP", rate=0.85867),
        RateRow(date="2026-09-11", base="EUR", quote="JPY", rate=179.18),
        RateRow(date="2026-09-11", base="EUR", quote="USD", rate=1.1627),
    ]
    sent = route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert sent["quotes"] == "GBP,JPY,USD"
    assert "date" not in sent


async def test_rates_historical_date_is_sent_as_a_query_param(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekday"))
    )

    rows = await client.rates(base="EUR", quotes=["GBP", "JPY", "USD"], date="2026-09-08")

    assert rows == [
        RateRow(date="2026-09-08", base="EUR", quote="GBP", rate=0.85862),
        RateRow(date="2026-09-08", base="EUR", quote="JPY", rate=179.41),
        RateRow(date="2026-09-08", base="EUR", quote="USD", rate=1.1621),
    ]
    assert route.calls.last.request.url.params["date"] == "2026-09-08"


async def test_rates_on_a_weekend_date_can_return_a_per_currency_mismatched_date(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    # The v2 quirk documented in docs/DECISIONS.md: ANG still carries the previous working day.
    respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_historical_weekend"))
    )

    rows = await client.rates(base="EUR", quotes=["ANG", "GBP", "USD"], date="2026-09-06")

    assert rows == [
        RateRow(date="2026-09-04", base="EUR", quote="ANG", rate=2.0813),
        RateRow(date="2026-09-06", base="EUR", quote="GBP", rate=0.85901),
        RateRow(date="2026-09-06", base="EUR", quote="USD", rate=1.1627),
    ]


async def test_rates_without_quotes_omits_the_quotes_param(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_latest"))
    )

    await client.rates()

    sent = route.calls.last.request.url.params
    assert sent["base"] == "EUR"
    assert "quotes" not in sent
    assert "date" not in sent


async def test_rates_raises_upstream_error_on_an_http_error_status(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(503, text="down"))

    with pytest.raises(UpstreamError) as exc:
        await client.rates(base="EUR", quotes=["USD"])

    assert str(exc.value) == f"{BASE_URL}/rates returned HTTP 503"
    assert exc.value.status_code == 503


async def test_rates_raises_upstream_error_on_http_400_exactly(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    # Pins the >= 400 boundary itself, not just a higher status already covered elsewhere.
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(400, text="bad request"))

    with pytest.raises(UpstreamError) as exc:
        await client.rates(base="EUR", quotes=["USD"])

    assert str(exc.value) == f"{BASE_URL}/rates returned HTTP 400"
    assert exc.value.status_code == 400


async def test_rates_raises_upstream_error_on_a_network_failure(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(side_effect=httpx.ConnectError("refused"))

    with pytest.raises(UpstreamError) as exc:
        await client.rates(base="EUR", quotes=["USD"])

    assert str(exc.value) == f"could not reach {BASE_URL}/rates: refused"


async def test_rates_raises_upstream_error_on_a_non_json_body(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, text="not json"))

    with pytest.raises(UpstreamError) as exc:
        await client.rates(base="EUR", quotes=["USD"])

    assert str(exc.value) == f"{BASE_URL}/rates returned a response that is not valid JSON"


async def test_rates_raises_upstream_error_on_a_malformed_shape(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json={"oops": True}))

    with pytest.raises(UpstreamError) as exc:
        await client.rates(base="EUR", quotes=["USD"])

    assert str(exc.value) == (
        f"malformed response from {BASE_URL}/rates: expected a JSON array of rate rows, got dict"
    )


# ---------------------------------------------------------------------------------------------
# rates_range()
# ---------------------------------------------------------------------------------------------


async def test_rates_range_parses_the_fixture(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d"))
    )

    rows = await client.rates_range(date_from="2026-08-10", date_to="2026-09-08", quotes=["USD"])

    assert len(rows) == 30
    assert rows[0] == RateRow(date="2026-08-10", base="EUR", quote="USD", rate=1.1553)
    assert rows[-1] == RateRow(date="2026-09-08", base="EUR", quote="USD", rate=1.1621)
    sent = route.calls.last.request.url.params
    assert sent["base"] == "EUR"  # the default, since no base was passed above
    assert sent["from"] == "2026-08-10"
    assert sent["to"] == "2026-09-08"
    assert sent["quotes"] == "USD"


async def test_rates_range_joins_multiple_quotes_with_a_comma(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d"))
    )

    await client.rates_range(date_from="2026-08-10", date_to="2026-09-08", quotes=["GBP", "USD"])

    assert route.calls.last.request.url.params["quotes"] == "GBP,USD"


async def test_rates_range_without_quotes_omits_the_quotes_param(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    route = respx_mock.get(f"{BASE_URL}/rates").mock(
        return_value=httpx.Response(200, json=_fixture("v2_rates_range_30d"))
    )

    await client.rates_range(date_from="2026-08-10", date_to="2026-09-08")

    assert "quotes" not in route.calls.last.request.url.params


async def test_rates_range_raises_upstream_error_on_a_malformed_shape(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(200, json={"oops": True}))

    with pytest.raises(UpstreamError) as exc:
        await client.rates_range(date_from="2026-08-10", date_to="2026-09-08")

    assert str(exc.value) == (
        f"malformed response from {BASE_URL}/rates: expected a JSON array of rate rows, got dict"
    )


async def test_rates_range_raises_upstream_error_on_an_http_error_status(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/rates").mock(return_value=httpx.Response(422, text="bad range"))

    with pytest.raises(UpstreamError) as exc:
        await client.rates_range(date_from="2026-08-10", date_to="2026-09-08")

    assert str(exc.value) == f"{BASE_URL}/rates returned HTTP 422"
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------------------------
# currencies()
# ---------------------------------------------------------------------------------------------


async def test_currencies_parses_the_fixture(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/currencies").mock(
        return_value=httpx.Response(200, json=_fixture("v2_currencies"))
    )

    rows = await client.currencies()

    assert len(rows) == 165
    assert rows[0] == CurrencyRow(
        iso_code="AED",
        iso_numeric="784",
        name="United Arab Emirates Dirham",
        symbol="د.إ",
        start_date="1996-04-11",
        end_date="2026-09-11",
    )
    assert any(row.iso_code == "EUR" for row in rows)


async def test_currencies_raises_upstream_error_on_an_http_error_status(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/currencies").mock(return_value=httpx.Response(500, text="down"))

    with pytest.raises(UpstreamError) as exc:
        await client.currencies()

    assert str(exc.value) == f"{BASE_URL}/currencies returned HTTP 500"


async def test_currencies_raises_upstream_error_on_a_malformed_shape(
    client: UpstreamClient, respx_mock: respx.MockRouter
) -> None:
    respx_mock.get(f"{BASE_URL}/currencies").mock(return_value=httpx.Response(200, json={}))

    with pytest.raises(UpstreamError) as exc:
        await client.currencies()

    assert str(exc.value) == (
        f"malformed response from {BASE_URL}/currencies: "
        "expected a JSON array of currencies, got dict"
    )
