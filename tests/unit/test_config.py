# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Settings: defaults, environment mapping and the HTTP-needs-a-token rule."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from mcp_frankfurter.__main__ import main
from mcp_frankfurter.config import Settings


def test_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.mcp_transport == "stdio"
    assert settings.mcp_host == "127.0.0.1"
    assert settings.mcp_port == 8000
    assert settings.mcp_auth_token is None
    assert settings.auth_token is None
    assert settings.upstream_base_url == "https://api.frankfurter.dev/v2"
    assert settings.http_timeout_seconds == 10


def test_http_transport_without_token_fails() -> None:
    with pytest.raises(ValidationError, match="MCP_AUTH_TOKEN is required"):
        Settings(_env_file=None, mcp_transport="streamable-http")


def test_http_transport_with_blank_token_fails() -> None:
    with pytest.raises(ValidationError, match="MCP_AUTH_TOKEN is required"):
        Settings(_env_file=None, mcp_transport="streamable-http", mcp_auth_token="   ")


def test_http_transport_with_token_is_valid() -> None:
    settings = Settings(_env_file=None, mcp_transport="streamable-http", mcp_auth_token=" s3cret ")

    assert settings.auth_token == "s3cret"
    assert "s3cret" not in repr(settings)  # SecretStr keeps it out of logs and dumps


def test_stdio_does_not_need_a_token() -> None:
    assert Settings(_env_file=None, mcp_transport="stdio").auth_token is None


def test_unknown_transport_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, mcp_transport="sse")


def test_values_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")
    monkeypatch.setenv("MCP_HOST", "0.0.0.0")
    monkeypatch.setenv("MCP_PORT", "9000")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "from-env")
    monkeypatch.setenv("UPSTREAM_BASE_URL", "https://api.example.test")
    monkeypatch.setenv("HTTP_TIMEOUT_SECONDS", "2.5")

    settings = Settings(_env_file=None)

    assert settings.mcp_transport == "streamable-http"
    assert settings.mcp_host == "0.0.0.0"
    assert settings.mcp_port == 9000
    assert settings.auth_token == "from-env"
    assert settings.upstream_base_url == "https://api.example.test"
    assert settings.http_timeout_seconds == 2.5


@pytest.mark.parametrize("port", ["0", "65536", "abc"])
def test_invalid_port_is_rejected(monkeypatch: pytest.MonkeyPatch, port: str) -> None:
    monkeypatch.setenv("MCP_PORT", port)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_main_fails_fast_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)  # no local .env can leak a token in
    monkeypatch.setenv("MCP_TRANSPORT", "streamable-http")

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "invalid configuration" in err
    assert "MCP_AUTH_TOKEN is required when MCP_TRANSPORT=streamable-http" in err
