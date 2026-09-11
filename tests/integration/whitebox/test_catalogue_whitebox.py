# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""SRV-01 by listing the tool catalogue directly on the `MCPServer` instance.

White-box: `mcp.list_tools()` is called in-process, with no JSON-RPC framing around it (compare
to tests/integration/blackbox/test_mcp_session.py, which lists tools over a real client session).
"""

from mcp_frankfurter.server import MAX_RANGE_DAYS, SERVER_NAME, mcp
from tests.integration.scenarios import scenario

TOOL_NAMES = {"convert", "latest_rates", "historical_rate", "rate_timeseries", "list_currencies"}


@scenario("SRV-01")
async def test_server_exposes_exactly_the_five_documented_tools() -> None:
    tools = {tool.name: tool for tool in await mcp.list_tools()}

    assert set(tools) == TOOL_NAMES
    assert mcp.name == SERVER_NAME

    convert = tools["convert"]
    assert set(convert.input_schema["properties"]) == {
        "amount",
        "from_currency",
        "to_currency",
        "date",
    }
    assert convert.input_schema["required"] == ["amount", "from_currency", "to_currency"]
    assert convert.output_schema is not None

    latest_rates = tools["latest_rates"]
    assert set(latest_rates.input_schema["properties"]) == {"base", "symbols"}
    assert latest_rates.input_schema["properties"]["base"]["default"] == "EUR"
    assert latest_rates.output_schema is not None

    historical_rate = tools["historical_rate"]
    assert set(historical_rate.input_schema["properties"]) == {"date", "base", "symbols"}
    assert historical_rate.input_schema["required"] == ["date"]

    rate_timeseries = tools["rate_timeseries"]
    assert set(rate_timeseries.input_schema["properties"]) == {
        "start_date",
        "end_date",
        "base",
        "symbol",
    }
    assert rate_timeseries.input_schema["required"] == ["start_date", "end_date"]
    assert rate_timeseries.input_schema["properties"]["symbol"]["default"] == "USD"
    # The range limit is advertised in the argument's own description, not just enforced
    # silently: the model needs it to avoid a doomed call.
    end_date_description = rate_timeseries.input_schema["properties"]["end_date"]["description"]
    assert str(MAX_RANGE_DAYS) in end_date_description

    list_currencies = tools["list_currencies"]
    assert list_currencies.input_schema.get("properties", {}) == {}
    assert list_currencies.output_schema is not None
