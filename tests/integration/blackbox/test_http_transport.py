# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""AUTH-01..AUTH-04 through the real streamable-HTTP app, `Starlette`'s `TestClient` as the user.

Black-box: `build_http_app` is the composition root's own function; nothing here reaches past the
ASGI boundary. Compare to test_auth_whitebox.py, which drives `BearerTokenMiddleware` alone.
"""

from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from mcp_frankfurter.__main__ import build_http_app
from mcp_frankfurter.config import Settings
from tests.integration.scenarios import scenario

TOKEN = "test-token"  # pragma: allowlist secret
AUTH = {"Authorization": f"Bearer {TOKEN}"}
MCP_HEADERS = {**AUTH, "Accept": "application/json, text/event-stream"}
INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "tests", "version": "0"},
    },
}


@pytest.fixture(scope="module")
def http_client() -> Iterator[TestClient]:
    # One app per module: the SDK's session manager can only be started once per MCPServer.
    settings = Settings(_env_file=None, mcp_transport="streamable-http", mcp_auth_token=TOKEN)
    with TestClient(build_http_app(settings)) as client:
        yield client


@scenario("AUTH-04")
def test_healthz_is_open_without_a_token(http_client: TestClient) -> None:
    response = http_client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@scenario("AUTH-01")
def test_mcp_endpoint_requires_a_token(http_client: TestClient) -> None:
    response = http_client.post("/mcp", json=INITIALIZE)

    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"
    assert response.headers["www-authenticate"].startswith("Bearer")


@scenario("AUTH-02")
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer wrong", "Accept": "application/json, text/event-stream"},
        {"Authorization": "Basic dGVzdA==", "Accept": "application/json, text/event-stream"},
    ],
    ids=["wrong-token", "wrong-scheme"],
)
def test_mcp_endpoint_rejects_an_unusable_token(
    http_client: TestClient, headers: dict[str, str]
) -> None:
    response = http_client.post("/mcp", json=INITIALIZE, headers=headers)

    assert response.status_code == 401


@scenario("AUTH-03")
def test_mcp_endpoint_accepts_the_correct_token(http_client: TestClient) -> None:
    # The full tool-call round trip over this exact JSON-RPC framing is proven once, over the
    # in-memory transport, by test_mcp_session.py; here the point is narrower: the bearer layer
    # in front of it lets a correctly authenticated request reach the server at all.
    response = http_client.post("/mcp", json=INITIALIZE, headers=MCP_HEADERS)

    assert response.status_code == 200, response.text
    assert "mcp-session-id" in response.headers
    assert "mcp-frankfurter" in response.text
