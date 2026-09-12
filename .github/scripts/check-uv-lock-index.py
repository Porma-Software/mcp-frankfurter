#!/usr/bin/env python3
# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Fail when a uv.lock references anything other than the public PyPI index.

    check-uv-lock-index.py [FILE ...]

With no arguments, resolves the repository root with `git rev-parse --show-toplevel`
and checks every tracked file whose basename is `uv.lock` (`git ls-files -z` run
against that root), so running this from any subdirectory still covers the whole
repository. With arguments, checks exactly those files instead (no git repository
required).

For every `[[package]]` table:
  - a `source` with a `registry` key must equal `https://pypi.org/simple` (a single
    trailing slash tolerated);
  - a `source` with a `url` key, the `sdist.url` and every `wheels[].url` must have
    the host `files.pythonhosted.org`.
Other source kinds (`editable`, `virtual`, `directory`, `path`, `git`) are not index
sources and pass untouched.

Never prints userinfo, passwords, paths or query strings from an offending URL: only
its hostname (plus `:port` when present). A file that cannot be read or parsed is
reported by path and exception class name only, never by its content.

Exit codes: 0 clean (including a repository with no uv.lock), 1 on offences, 2 when a
file cannot be read or parsed.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

PYPI_SIMPLE = "https://pypi.org/simple"
FILES_HOST = "files.pythonhosted.org"


def host_of(url: str) -> str:
    """The URL's hostname plus :port when present — never scheme, userinfo, password,
    path or query, so a mirror's embedded credentials never reach the output."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    return f"{host}:{parts.port}" if parts.port else host


def discover_targets() -> list[tuple[Path, str]]:
    """Every tracked uv.lock under the current repository, as (path, display) pairs
    where display is the path relative to the repository root."""
    try:
        root_result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(
            f"check-uv-lock-index.py: not a git repository: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    root = Path(root_result.stdout.strip())

    ls_result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    )
    entries = [e for e in ls_result.stdout.split("\0") if e]
    return [(root / e, e) for e in entries if PurePosixPath(e).name == "uv.lock"]


def check_document(doc: dict, display: str) -> list[str]:
    """Offense lines for one already-parsed uv.lock document."""
    offenses: list[str] = []
    for package in doc.get("package", []):
        name = package.get("name", "?")
        source = package.get("source") or {}

        if "registry" in source:
            registry = source["registry"]
            normalized = registry.removesuffix("/")
            if normalized != PYPI_SIMPLE:
                offenses.append(f"{display}: {name}: registry host {host_of(registry)}")
        elif "url" in source:
            host = host_of(source["url"])
            if host != FILES_HOST:
                offenses.append(f"{display}: {name}: file host {host}")
        # Other source kinds (editable, virtual, directory, path, git) are not index
        # sources: nothing to check.

        sdist = package.get("sdist")
        if isinstance(sdist, dict) and "url" in sdist:
            host = host_of(sdist["url"])
            if host != FILES_HOST:
                offenses.append(f"{display}: {name}: file host {host}")

        for wheel in package.get("wheels") or []:
            if isinstance(wheel, dict) and "url" in wheel:
                host = host_of(wheel["url"])
                if host != FILES_HOST:
                    offenses.append(f"{display}: {name}: file host {host}")

    return offenses


def main(argv: list[str]) -> int:
    targets = [(Path(arg), arg) for arg in argv] if argv else discover_targets()

    total_offenses = 0
    had_error = False
    for path, display in targets:
        try:
            with path.open("rb") as fh:
                doc = tomllib.load(fh)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            print(f"{display}: {type(exc).__name__}")
            had_error = True
            continue

        offenses = check_document(doc, display)
        for line in offenses:
            print(line)
        total_offenses += len(offenses)

    if total_offenses:
        print(
            f"{total_offenses} offending source(s); "
            "relock with: rm uv.lock && env -u UV_EXTRA_INDEX_URL uv lock"
        )

    if had_error:
        return 2
    if total_offenses:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
