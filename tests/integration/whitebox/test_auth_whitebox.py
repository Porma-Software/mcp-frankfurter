# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""AUTH-01..AUTH-04 by driving `BearerTokenMiddleware` directly, no transport around it.

White-box: the middleware is the adapter; these tests build it over a bare ASGI app instead of
the composition root's real app (see test_http_transport.py in the black-box suite for that).
"""

import pytest
from starlette.responses import JSONResponse
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from mcp_frankfurter.auth import BearerTokenMiddleware
from tests.integration.scenarios import scenario

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


async def echo_app(scope: Scope, receive: Receive, send: Send) -> None:
    await JSONResponse({"path": scope["path"], "method": scope["method"]})(scope, receive, send)


@pytest.fixture
def client() -> TestClient:
    return TestClient(BearerTokenMiddleware(echo_app, token=TOKEN))


@scenario("AUTH-01")
def test_missing_token_is_401(client: TestClient) -> None:
    response = client.get("/mcp")

    assert response.status_code == 401
    assert response.json() == {
        "error": "unauthorized",
        "detail": "Authorization: Bearer <token> header required",
    }
    assert response.headers["www-authenticate"].startswith("Bearer")


@scenario("AUTH-02")
@pytest.mark.parametrize(
    "header",
    ["Bearer wrong", "Bearer test-token-plus", "Bearer test-toke", "Basic dGVzdA==", TOKEN, ""],
)
def test_wrong_token_is_401(client: TestClient, header: str) -> None:
    assert client.post("/mcp", headers={"Authorization": header}).status_code == 401


@scenario("AUTH-04")
def test_healthz_is_open_for_get_only(client: TestClient) -> None:
    assert client.get("/healthz").status_code == 200
    assert client.post("/healthz").status_code == 401


@scenario("AUTH-03")
def test_correct_token_passes(client: TestClient) -> None:
    response = client.post("/mcp", headers=AUTH)

    assert response.status_code == 200
    assert response.json() == {"path": "/mcp", "method": "POST"}


def test_scheme_is_case_insensitive(client: TestClient) -> None:
    assert client.get("/mcp", headers={"Authorization": f"bearer {TOKEN}"}).status_code == 200


def test_authorization_splits_on_the_first_space_only() -> None:
    # A token containing a space is unusual but not forbidden; the header is split on the FIRST
    # space (scheme, then the rest), not the last one. This tells `partition(" ")` apart from
    # `rpartition(" ")`: with the latter "Bearer to ken" would split into scheme "Bearer to" and
    # credentials "ken", which is not "bearer" and would be rejected.
    spaced_token = "to ken"  # pragma: allowlist secret
    middleware_client = TestClient(BearerTokenMiddleware(echo_app, token=spaced_token))

    response = middleware_client.post("/mcp", headers={"Authorization": f"Bearer {spaced_token}"})

    assert response.status_code == 200


def test_websocket_is_refused(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/mcp"):
            pass
    assert exc.value.code == 1008


def test_blank_token_is_refused_at_construction() -> None:
    with pytest.raises(ValueError, match=r"^BearerTokenMiddleware needs a non-empty token$"):
        BearerTokenMiddleware(echo_app, token="   ")
