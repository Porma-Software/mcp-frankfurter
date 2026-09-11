# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Shared fixtures: a clean environment and a fresh upstream client per test."""

from collections.abc import AsyncIterator

import pytest

from mcp_frankfurter import server
from mcp_frankfurter.upstream import UpstreamClient

SETTINGS_ENV_VARS = (
    "MCP_TRANSPORT",
    "MCP_HOST",
    "MCP_PORT",
    "MCP_AUTH_TOKEN",
    "UPSTREAM_BASE_URL",
    "HTTP_TIMEOUT_SECONDS",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
async def upstream_client() -> AsyncIterator[UpstreamClient]:
    client = UpstreamClient(base_url="https://api.frankfurter.dev/v2", timeout_seconds=5)
    server.set_client(client)
    yield client
    await client.aclose()
    server.set_client(None)
