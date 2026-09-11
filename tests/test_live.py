# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Smoke test against the real upstream. Deselected by default; run with `uv run pytest -m live`.

Proves `UPSTREAM_BASE_URL` (see docs/DECISIONS.md for the API version decision) still answers
with the shape the mappers will parse. It is a canary, not a test suite: one cheap call, no
tool-specific assertions. Once the Frankfurter tools land, extend this with one cheap call per
tool instead of hitting the upstream client's transport directly.
"""

import httpx
import pytest

from mcp_frankfurter.config import Settings

pytestmark = pytest.mark.live


async def test_currencies_endpoint_is_reachable() -> None:
    settings = Settings()

    async with httpx.AsyncClient(base_url=settings.upstream_base_url, timeout=10) as client:
        response = await client.get("/currencies")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert any(entry["iso_code"] == "EUR" for entry in body)
