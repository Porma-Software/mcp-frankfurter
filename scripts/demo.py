# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Demo: a plain MCP client talking to this server over stdio, exactly as Claude would.

Spawns ``python -m mcp_frankfurter`` as a subprocess (the ``stdio`` transport, the default —
see ``docs/DECISIONS.md``) and calls three tools against the real Frankfurter API: ``latest_rates``
for USD and GBP, ``convert`` to turn 1,500 EUR into US dollars, and ``rate_timeseries`` for GBP
over the last 30 days. This is what ``docs/demo.gif`` records (``docs/demo.tape``, rendered with
``charmbracelet/vhs``) — a real run against the real server and the real upstream API, never faked.

    uv run python scripts/demo.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date, timedelta
from typing import Any

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent


def _error_text(result: CallToolResult) -> str:
    content = result.content[0]
    assert isinstance(content, TextContent)
    return content.text


async def _run_tool(client: Client, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await client.call_tool(name, arguments)
    if result.is_error:
        raise RuntimeError(_error_text(result))
    assert result.structured_content is not None
    return result.structured_content


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_frankfurter"])

    # The server logs to stderr by design (__main__.py: "stdout is the protocol channel"), which
    # would otherwise interleave raw HTTP request logging into this demo's own readable output.
    # errlog=devnull only discards that stream for the recording; a real crash still raises
    # through the client below and prints to this script's own stderr, untouched.
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        async with Client(stdio_client(params, errlog=devnull), mode="legacy") as client:
            print("mcp-frankfurter demo - a real MCP client, three real tool calls\n")

            print("> latest_rates(base='EUR', symbols=['USD', 'GBP'])")
            rates = await _run_tool(
                client, "latest_rates", {"base": "EUR", "symbols": ["USD", "GBP"]}
            )
            for code, rate in sorted(rates["rates"].items()):
                print(f"  1 EUR = {rate} {code}")
            print(f"  (rate date: {rates['rate_date']})\n")

            print("> convert(amount=1500, from_currency='EUR', to_currency='USD')")
            conversion = await _run_tool(
                client, "convert", {"amount": 1500, "from_currency": "EUR", "to_currency": "USD"}
            )
            print(
                f"  {conversion['amount']:.2f} {conversion['from_currency']} = "
                f"{conversion['converted']:.2f} {conversion['to_currency']} "
                f"(rate {conversion['rate']}, as of {conversion['rate_date']})\n"
            )

            end = date.today()
            start = end - timedelta(days=30)
            print(f"> rate_timeseries(start_date='{start}', end_date='{end}', symbol='GBP')")
            series = await _run_tool(
                client,
                "rate_timeseries",
                {"start_date": str(start), "end_date": str(end), "base": "EUR", "symbol": "GBP"},
            )
            span = f"{series['start_date']} to {series['end_date']}"
            print(f"  {len(series['points'])} published rates from {span}")
            print(f"  min {series['min']}  max {series['max']}  average {series['average']:.5f}")


if __name__ == "__main__":
    asyncio.run(main())
