# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Entry point for the `mcp-frankfurter` console script and `python -m mcp_frankfurter`."""

import sys

import uvicorn
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_frankfurter.auth import BearerTokenMiddleware
from mcp_frankfurter.config import Settings
from mcp_frankfurter.server import mcp, set_client
from mcp_frankfurter.upstream import UpstreamClient

HEALTH_PATH = "/healthz"


async def healthz(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok"})


def build_http_app(settings: Settings) -> Starlette:
    """Streamable-HTTP ASGI app: MCP at /mcp, open GET /healthz, bearer auth on everything else."""
    token = settings.auth_token
    if token is None:  # Settings already enforces it; kept so the type checker and reader know
        raise ValueError("MCP_AUTH_TOKEN is required for the HTTP transport")
    # The SDK app owns the session-manager lifespan, so it stays the root app; we add to it.
    app = mcp.streamable_http_app(
        host=settings.mcp_host,
        # For localhost binds the SDK would otherwise enable its DNS-rebinding guard, which
        # validates Host/Origin against 127.0.0.1/localhost and answers 421 behind any real
        # hostname or reverse proxy. The bearer token in auth.py already defeats DNS rebinding:
        # a rebound page cannot know the token.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    app.add_route(HEALTH_PATH, healthz, methods=["GET"])
    app.add_middleware(BearerTokenMiddleware, token=token, exempt_paths={HEALTH_PATH})
    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as exc:
        # Messages only: pydantic's default rendering echoes the raw input, secrets included.
        problems = "; ".join(str(err["msg"]) for err in exc.errors(include_input=False))
        print(f"mcp-frankfurter: invalid configuration: {problems}", file=sys.stderr)
        raise SystemExit(2) from None

    set_client(UpstreamClient.from_settings(settings))
    if settings.mcp_transport == "streamable-http":
        uvicorn.run(
            build_http_app(settings),
            host=settings.mcp_host,
            port=settings.mcp_port,
            log_level="info",
        )
    else:
        mcp.run(transport="stdio")  # logs go to stderr; stdout is the protocol channel


if __name__ == "__main__":
    main()
