# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""AUTH-05's white-box shape: the tool catalogue reached in-process, no bearer layer in front.

No tool is defined yet (the Frankfurter tools land in the next development slice), but the point
of AUTH-05 still holds without one: `mcp.list_tools()` called directly needs no `Authorization`
header at all, which is the white-box shape of "a stdio session trusts the parent process, no
token required" — compare to tests/integration/blackbox/test_mcp_session.py, which proves the
same thing over a real in-memory client session.
"""

from mcp_frankfurter.server import SERVER_NAME, mcp
from tests.integration.scenarios import scenario


@scenario("AUTH-05")
async def test_tool_catalogue_is_reachable_with_no_bearer_layer() -> None:
    tools = await mcp.list_tools()

    assert tools == []  # empty until the Frankfurter tools land; see docs/DECISIONS.md
    assert mcp.name == SERVER_NAME
