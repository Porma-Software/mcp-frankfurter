# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
# Renders docs/demo.gif; never shipped, never part of the server image (see ../Dockerfile).
#
# ghcr.io/charmbracelet/vhs has no Python, and scripts/demo.py needs one -- add uv, which then
# fetches its own interpreter (see the `uv python install` below) since this base image ships
# neither Python nor a package manager for it.
#
# The project is COPYed in and `uv sync` runs at build time, inside the image's own filesystem --
# never bind-mounted, the same rule scripts/check_mutants.py documents for mutmut ("its .venv is
# not portable across platforms"): a host bind mount of the whole tree lets the Linux container
# overwrite a Windows-built .venv in place. `--no-dev` skips pytest/mutmut/ruff/mypy (and their
# transitive deps, e.g. mutmut's `textual`) -- the demo only needs the runtime dependencies.
#
# `docs/` is in .dockerignore (kept out of the real server image, see ../Dockerfile) so it is
# never COPYed here either -- it is bind-mounted at run time instead, which is also how the
# rendered gif gets back out to the host:
#
#   docker build -t mcp-frankfurter-vhs -f docs/vhs.Dockerfile .
#   docker run --rm -v "$PWD/docs":/work/docs mcp-frankfurter-vhs docs/demo.tape

FROM ghcr.io/charmbracelet/vhs:latest

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/
RUN uv python install 3.14

WORKDIR /work
COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
COPY src ./src
RUN uv sync --locked --no-dev
COPY scripts ./scripts
