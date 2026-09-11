# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Async client for the upstream HTTP API (Frankfurter `v2`, see `docs/DECISIONS.md`).

The ONLY module that knows the upstream URL shapes and response formats. Three endpoint methods,
all reachable through `v2/rates` and `v2/currencies`:

- `rates(base, quotes, date)`: `date=None` is "latest"; given, it is one historical date. Both
  share the same upstream endpoint and response shape (see `mappers.parse_rate_rows`).
- `rates_range(base, quotes, date_from, date_to)`: a date range, same response shape as `rates`.
- `currencies()`: the ISO 4217 catalogue.

Every method returns `mappers.py` domain records or raises `UpstreamError` — never the raw
`httpx.Response` or JSON. `server.py`'s five tools call these through the `to_*` mapper
functions; each method is also exercised directly by
`tests/integration/whitebox/test_upstream_whitebox.py` against the fixtures in `tests/fixtures/`.
"""

from collections.abc import Sequence

import httpx

from mcp_frankfurter.config import Settings
from mcp_frankfurter.mappers import CurrencyRow, RateRow, parse_currency_rows, parse_rate_rows

USER_AGENT = "mcp-frankfurter/0.1"

__all__ = ["USER_AGENT", "UpstreamClient", "UpstreamError"]


class UpstreamError(Exception):
    """The upstream API did not answer usefully: non-2xx status, network error or bad payload."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamClient:
    """Thin httpx wrapper around the Frankfurter `v2` API."""

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

    async def _get_json(self, path: str, params: dict[str, str]) -> object:
        url = f"{self._base_url}{path}"
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamError(f"could not reach {url}: {exc}") from exc
        if response.status_code >= 400:
            raise UpstreamError(
                f"{url} returned HTTP {response.status_code}", status_code=response.status_code
            )
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError(f"{url} returned a response that is not valid JSON") from exc

    async def rates(
        self, *, base: str = "EUR", quotes: Sequence[str] | None = None, date: str | None = None
    ) -> list[RateRow]:
        """`GET /rates`: `date=None` is the latest rate, otherwise one historical date."""
        params: dict[str, str] = {"base": base}
        if quotes:
            params["quotes"] = ",".join(quotes)
        if date is not None:
            params["date"] = date
        payload = await self._get_json("/rates", params)
        try:
            return parse_rate_rows(payload)
        except ValueError as exc:
            raise UpstreamError(f"malformed response from {self._base_url}/rates: {exc}") from exc

    async def rates_range(
        self,
        *,
        date_from: str,
        date_to: str,
        base: str = "EUR",
        quotes: Sequence[str] | None = None,
    ) -> list[RateRow]:
        """`GET /rates?from=...&to=...`: one row per published date in `[date_from, date_to]`."""
        params: dict[str, str] = {"base": base, "from": date_from, "to": date_to}
        if quotes:
            params["quotes"] = ",".join(quotes)
        payload = await self._get_json("/rates", params)
        try:
            return parse_rate_rows(payload)
        except ValueError as exc:
            raise UpstreamError(f"malformed response from {self._base_url}/rates: {exc}") from exc

    async def currencies(self) -> list[CurrencyRow]:
        """`GET /currencies`: the ISO 4217 catalogue Frankfurter quotes against the euro."""
        payload = await self._get_json("/currencies", {})
        try:
            return parse_currency_rows(payload)
        except ValueError as exc:
            raise UpstreamError(
                f"malformed response from {self._base_url}/currencies: {exc}"
            ) from exc
