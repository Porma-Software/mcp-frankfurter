# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Async client for the upstream HTTP API (Frankfurter).

This is the ONLY module that will know the upstream URL shapes and response formats once the
Frankfurter-specific methods land (see docs/DECISIONS.md for the API version probe and the
choice it settled on). For this scaffold it owns just the generic HTTP wiring shared by every
future method: configuration, lifecycle and the one error type every upstream call will raise.
"""

import httpx

from mcp_frankfurter.config import Settings

USER_AGENT = "mcp-frankfurter/0.1"

__all__ = ["USER_AGENT", "UpstreamClient", "UpstreamError"]


class UpstreamError(Exception):
    """The upstream API did not answer usefully: non-2xx status, network error or bad payload."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamClient:
    """Thin httpx wrapper around the Frankfurter API. Endpoint methods land in the next slice."""

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        self._client = httpx.AsyncClient(
            headers=headers, timeout=timeout_seconds, transport=transport
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> "UpstreamClient":
        return cls(
            base_url=settings.upstream_base_url, timeout_seconds=settings.http_timeout_seconds
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "UpstreamClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()
