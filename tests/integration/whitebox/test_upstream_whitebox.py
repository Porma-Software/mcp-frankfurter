# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""The outbound adapter's generic wiring: settings, headers, lifecycle.

White-box, untagged: no user scenario attaches to wiring on its own. The endpoint methods — and
the request/response/error-mapping tests that go with them — land in the next development
slice, once a tool in server.py actually calls them; see docs/DECISIONS.md for the chosen
Frankfurter API version.
"""

from mcp_frankfurter.config import Settings
from mcp_frankfurter.upstream import USER_AGENT, UpstreamClient, UpstreamError


async def test_base_url_strips_a_trailing_slash() -> None:
    # A real base URL usually arrives with one; rstrip("/") must not eat into the scheme.
    async with UpstreamClient(base_url="https://api.frankfurter.dev/v2/") as client:
        assert client.base_url == "https://api.frankfurter.dev/v2"


def test_timeout_seconds_is_stored() -> None:
    assert UpstreamClient(base_url="https://x.test", timeout_seconds=2.5).timeout_seconds == 2.5


def test_default_timeout_is_ten_seconds() -> None:
    assert UpstreamClient(base_url="https://x.test").timeout_seconds == 10.0


def test_user_agent_is_set_on_the_http_client() -> None:
    client = UpstreamClient(base_url="https://x.test")

    assert client._client.headers["User-Agent"] == USER_AGENT


async def test_from_settings_wires_base_url_and_timeout() -> None:
    settings = Settings(
        _env_file=None,
        upstream_base_url="https://upstream.example.test/",
        http_timeout_seconds=3.5,
    )

    async with UpstreamClient.from_settings(settings) as client:
        assert client.base_url == "https://upstream.example.test"
        assert client.timeout_seconds == 3.5


async def test_aclose_closes_the_underlying_http_client() -> None:
    client = UpstreamClient(base_url="https://x.test")

    await client.aclose()

    assert client._client.is_closed is True


async def test_aclose_is_safe_to_call_twice() -> None:
    # httpx.AsyncClient.aclose() already tolerates a second call; this pins that UpstreamClient
    # does not add a guard of its own that would break on it.
    client = UpstreamClient(base_url="https://x.test")
    await client.aclose()

    await client.aclose()


def test_upstream_error_carries_a_message_and_an_optional_status_code() -> None:
    bare = UpstreamError("boom")
    assert str(bare) == "boom"
    assert bare.status_code is None

    with_status = UpstreamError("boom", status_code=503)
    assert with_status.status_code == 503
