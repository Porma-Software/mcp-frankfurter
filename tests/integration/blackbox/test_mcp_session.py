# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""AUTH-05 through a real MCP client session.

Black-box: only `mcp.client.Client` is used, never a tool function or `UpstreamClient` directly.
`mode="legacy"` runs the server behind in-memory streams with JSON-RPC framing and the initialize
handshake — exactly what a stdio or HTTP client does. The default "auto" mode dispatches
in-process without serialising anything, which would hide schema regressions, so it is never used
here.

No tool is registered yet (the Frankfurter tools land in the next development slice); this still
proves the shape AUTH-05 is about: the session opens, negotiates and lists its (empty) tool
catalogue with no bearer layer at all — `stdio` trusts the parent process that launched it.
"""

from mcp.client import Client

from mcp_frankfurter.server import SERVER_NAME, mcp
from tests.integration.scenarios import scenario


def connect() -> Client:
    return Client(mcp, mode="legacy")


@scenario("AUTH-05")
async def test_session_works_with_no_token_at_all() -> None:
    async with connect() as client:
        assert client.server_info is not None
        assert client.server_info.name == SERVER_NAME
        listed = await client.list_tools()

    assert listed.tools == []


async def test_an_unknown_tool_name_is_an_error_result() -> None:
    # Not a catalogue scenario (there is no user action that names a tool): a protocol-level
    # safety net, kept next to the scenario-tagged test it shares its connect() helper with.
    async with connect() as client:
        result = await client.call_tool("no_such_tool", {})

    assert result.is_error is True
