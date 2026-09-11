# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Runtime configuration, read from environment variables and an optional `.env` file.

Variable names are the upper-cased field names (MCP_TRANSPORT, UPSTREAM_BASE_URL, ...).
"""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Transport = Literal["stdio", "streamable-http"]


class Settings(BaseSettings):
    """Every knob of the server. Instantiate once at startup; it fails fast on bad config."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # MCP transport
    mcp_transport: Transport = "stdio"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8000, ge=1, le=65535)
    # Required for streamable-http: every request must carry `Authorization: Bearer <token>`.
    mcp_auth_token: SecretStr | None = None

    # Upstream API wrapped by the tools (see upstream.py). Frankfurter needs no key; the default
    # points at the API version this server was built against — see docs/DECISIONS.md.
    upstream_base_url: str = "https://api.frankfurter.dev/v2"
    http_timeout_seconds: float = Field(default=10.0, gt=0)

    @property
    def auth_token(self) -> str | None:
        """The bearer token as plain text, or None when unset or blank."""
        if self.mcp_auth_token is None:
            return None
        return self.mcp_auth_token.get_secret_value().strip() or None

    @model_validator(mode="after")
    def _require_token_for_http(self) -> Self:
        # stdio trusts the parent process, as every MCP client does; HTTP is network-reachable.
        if self.mcp_transport == "streamable-http" and self.auth_token is None:
            raise ValueError(
                "MCP_AUTH_TOKEN is required when MCP_TRANSPORT=streamable-http: the HTTP "
                "transport is reachable over the network and every request must be authenticated"
            )
        return self
