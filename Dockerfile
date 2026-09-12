FROM python:3.14-slim

LABEL org.opencontainers.image.source="https://github.com/Porma-Software/mcp-frankfurter" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.title="mcp-frankfurter" \
      org.opencontainers.image.description="MCP server exposing the Frankfurter API (ECB euro reference exchange rates) as tools."

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so they cache independently of the source.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# README.md and LICENSE are part of the package metadata.
COPY README.md LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

RUN useradd --system --uid 10001 --create-home app && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

EXPOSE 8000

# Shell form so MCP_PORT is honoured; the slim image has no curl.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"MCP_PORT\", \"8000\")}/healthz', timeout=2)"

CMD ["mcp-frankfurter"]
