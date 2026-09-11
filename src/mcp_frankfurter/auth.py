# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Bearer-token authentication for the HTTP transport.

Pure ASGI middleware (not BaseHTTPMiddleware) so streamed responses (SSE) pass through untouched.
"""

import hmac
from collections.abc import Iterable

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset({"/healthz"})


class BearerTokenMiddleware:
    """Reject every HTTP request that does not carry `Authorization: Bearer <token>`.

    `GET` on an exempt path (the health check) passes without a token. The lifespan scope passes
    through; websockets are refused because nothing behind this middleware serves them.
    """

    def __init__(
        self, app: ASGIApp, token: str, exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS
    ) -> None:
        if not token.strip():
            raise ValueError("BearerTokenMiddleware needs a non-empty token")
        self._app = app
        self._token = token.strip().encode()
        self._exempt_paths = frozenset(exempt_paths)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await receive()  # the handshake; closing before accept rejects it
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http" or self._is_exempt(scope) or self._is_authorized(scope):
            await self._app(scope, receive, send)
            return
        response = JSONResponse(
            {"error": "unauthorized", "detail": "Authorization: Bearer <token> header required"},
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="mcp"'},
        )
        await response(scope, receive, send)

    def _is_exempt(self, scope: Scope) -> bool:
        return scope.get("method") == "GET" and scope["path"] in self._exempt_paths

    def _is_authorized(self, scope: Scope) -> bool:
        scheme, _, credentials = Headers(scope=scope).get("authorization", "").partition(" ")
        if scheme.lower() != "bearer":
            return False
        return hmac.compare_digest(credentials.strip().encode(), self._token)
