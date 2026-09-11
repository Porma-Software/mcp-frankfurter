# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Smoke tests against the real upstream. Deselected by default; run with `uv run pytest -m live`.

One cheap call per tool, through a real in-memory MCP client session (`Client(mcp, mode="legacy")`,
the same shape `tests/integration/blackbox/test_mcp_session.py` uses) so this exercises the whole
stack -- tool, `UpstreamClient`, mappers -- against the real Frankfurter API instead of a `respx`
mock. These are canaries, not a scenario suite: no tool-specific assertions beyond "the shape the
mappers expect came back", and they are never run in CI (see docs/scenarios.md "Scope").
"""

from datetime import date, timedelta

import pytest
from mcp.client import Client
from mcp.types import CallToolResult, TextContent

from mcp_frankfurter.server import mcp

pytestmark = pytest.mark.live


def connect() -> Client:
    return Client(mcp, mode="legacy")


def text_of(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


async def test_convert_is_reachable() -> None:
    async with connect() as client:
        result = await client.call_tool(
            "convert", {"amount": 1.0, "from_currency": "EUR", "to_currency": "USD"}
        )

    assert result.is_error is False, text_of(result)
    assert result.structured_content is not None
    assert result.structured_content["converted"] > 0


async def test_latest_rates_is_reachable() -> None:
    async with connect() as client:
        result = await client.call_tool("latest_rates", {"base": "EUR", "symbols": ["USD"]})

    assert result.is_error is False, text_of(result)
    assert result.structured_content is not None
    assert result.structured_content["rates"]["USD"] > 0


async def test_historical_rate_is_reachable() -> None:
    a_recent_working_day = (date.today() - timedelta(days=7)).isoformat()

    async with connect() as client:
        result = await client.call_tool(
            "historical_rate",
            {"date": a_recent_working_day, "base": "EUR", "symbols": ["USD"]},
        )

    assert result.is_error is False, text_of(result)
    assert result.structured_content is not None
    assert result.structured_content["rates"]["USD"] > 0


async def test_rate_timeseries_is_reachable() -> None:
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=2)).isoformat()

    async with connect() as client:
        result = await client.call_tool(
            "rate_timeseries",
            {"start_date": start, "end_date": end, "base": "EUR", "symbol": "USD"},
        )

    assert result.is_error is False, text_of(result)
    assert result.structured_content is not None
    assert len(result.structured_content["points"]) >= 1


async def test_list_currencies_is_reachable() -> None:
    async with connect() as client:
        result = await client.call_tool("list_currencies", {})

    assert result.is_error is False, text_of(result)
    assert result.structured_content is not None
    codes = {entry["code"] for entry in result.structured_content["result"]}
    assert "EUR" in codes
