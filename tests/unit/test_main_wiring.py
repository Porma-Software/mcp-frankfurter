# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Composition root: which transport `main()` starts, and the upstream client it injects.

`build_http_app`'s user-facing behaviour (401, /healthz, the MCP endpoint) is proven by the
scenario-tagged tests in tests/integration/; here we only pin down the wiring decisions main()
makes, which have no user scenario of their own.
"""

from pathlib import Path
from typing import Any, NoReturn

import pytest
from starlette.applications import Starlette

from mcp_frankfurter import __main__ as entry_point
from mcp_frankfurter import server
from mcp_frankfurter.config import Settings
from mcp_frankfurter.upstream import UpstreamClient

# Trailing slash on purpose: proves main() wires UpstreamClient through the same rstrip("/") path
# a real base URL (which usually arrives with one) would take.
UPSTREAM_URL = "https://upstream.example.test/"


def _unexpected(*_: object, **__: object) -> NoReturn:
    raise AssertionError("the other transport must not be started")


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # No .env of the developer's machine, a recognisable upstream to assert the injection.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("UPSTREAM_BASE_URL", UPSTREAM_URL)


async def test_main_runs_stdio_by_default(
    isolated: None, monkeypatch: pytest.MonkeyPatch, upstream_client: UpstreamClient
) -> None:
    started: list[dict[str, Any]] = []
    monkeypatch.setattr(entry_point.mcp, "run", lambda **kwargs: started.append(kwargs))
    monkeypatch.setattr(entry_point.uvicorn, "run", _unexpected)

    entry_point.main()

    assert started == [{"transport": "stdio"}]
    injected = server.get_client()
    assert injected is not upstream_client  # main() replaced the test's client with its own
    assert injected.base_url == UPSTREAM_URL.rstrip("/")  # and it points at the configured one
    await server.close_client()


async def test_main_serves_http_on_the_configured_host_and_port(
    isolated: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "t0ken")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "9100")
    served: dict[str, Any] = {}
    monkeypatch.setattr(entry_point.mcp, "run", _unexpected)
    monkeypatch.setattr(
        entry_point.uvicorn, "run", lambda app, **kwargs: served.update(app=app, **kwargs)
    )

    entry_point.main()

    assert served["host"] == "0.0.0.0"
    assert served["port"] == 9100
    assert isinstance(served["app"], Starlette)
    await server.close_client()


def test_build_http_app_refuses_to_run_without_a_token() -> None:
    # Unreachable through main() (Settings enforces it); the guard keeps the app honest if a
    # caller builds it directly. Exact message: a substring match would still pass against
    # mutmut's mutated "XXMCP_AUTH_TOKEN...XX" literal, proving nothing about it.
    with pytest.raises(ValueError) as exc:
        entry_point.build_http_app(Settings(_env_file=None))
    assert str(exc.value) == "MCP_AUTH_TOKEN is required for the HTTP transport"


async def test_get_client_builds_one_default_from_the_environment(isolated: None) -> None:
    server.set_client(None)

    client = server.get_client()

    assert server.get_client() is client  # built once, then reused by every tool
    assert client.base_url == UPSTREAM_URL.rstrip("/")
    await server.close_client()


async def test_close_client_is_idempotent(isolated: None) -> None:
    await server.close_client()

    await server.close_client()  # a second shutdown must not explode

    assert server.get_client() is not None  # and a later call still gets a working client
    await server.close_client()
