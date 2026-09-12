# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""FX-28..FX-29 by calling `list_currencies` directly, the upstream HTTP boundary mocked."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from mcp.server.mcpserver.exceptions import ToolError

from mcp_frankfurter.server import list_currencies
from tests.integration.scenarios import scenario

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
BASE_URL = "https://api.frankfurter.dev/v2"


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def currencies_route(respx_mock: respx.MockRouter) -> respx.Route:
    return respx_mock.get(f"{BASE_URL}/currencies")


@scenario("FX-28")
async def test_list_currencies_happy_path(currencies_route: respx.Route) -> None:
    currencies_route.mock(return_value=httpx.Response(200, json=_fixture("v2_currencies")))

    result = await list_currencies()

    assert len(result) == 165
    assert {"code": "USD", "name": "United States Dollar"} in result
    assert {"code": "EUR", "name": "Euro"} in result
    assert "symbol" not in result[0]


@scenario("FX-29")
async def test_list_currencies_upstream_error_is_a_tool_error(
    currencies_route: respx.Route,
) -> None:
    currencies_route.mock(return_value=httpx.Response(500, text="down"))

    with pytest.raises(ToolError) as exc:
        await list_currencies()

    assert str(exc.value) == (
        f"currency catalogue service unavailable: {BASE_URL}/currencies returned HTTP 500: down"
    )
