# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""The MCP server: tool definitions on top of the upstream client.

No tool is registered yet — this scaffold slice only wires the composition root and the
transport. The Frankfurter tools (see docs/DECISIONS.md for the chosen API version) land in the
next development slice, each as a thin `@mcp.tool()` function on top of `upstream.py`, following
`.claude/skills/mcp-hexagonal/SKILL.md`.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer

from mcp_frankfurter.config import Settings
from mcp_frankfurter.upstream import UpstreamClient

SERVER_NAME = "mcp-frankfurter"

__all__ = ["SERVER_NAME", "mcp"]


# Upstream client shared by the tools. main() injects one built from the validated Settings;
# tests inject their own; anything else gets a lazily built default.
_client: UpstreamClient | None = None


def get_client() -> UpstreamClient:
    global _client
    if _client is None:
        _client = UpstreamClient.from_settings(Settings())
    return _client


def set_client(client: UpstreamClient | None) -> None:
    global _client
    _client = client


async def close_client() -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()


@asynccontextmanager
async def _lifespan(_: "MCPServer[None]") -> AsyncIterator[None]:
    try:
        yield
    finally:
        await close_client()


# Transport options (host, port, DNS-rebinding guard) belong to the transport, not to the server:
# see build_http_app() in __main__.py.
mcp: "MCPServer[None]" = MCPServer(
    SERVER_NAME,
    instructions=(
        "Euro reference exchange-rate tools backed by the Frankfurter API (ECB data). No tool "
        "is registered yet in this scaffold; see docs/DECISIONS.md for the chosen API version."
    ),
    lifespan=_lifespan,
)
