# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""GHCR release workflow and image labels: static checks against `.github/workflows/release.yml`
and the `Dockerfile` as plain text (no YAML parser, no new dependency).

Publishing the image on a version tag has no MCP client-facing behaviour of its own — like the
composition-root wiring in `test_main_wiring.py`, it carries no `docs/scenarios.md` catalogue ID
(see that file's "Scope" section) and lives here in `tests/unit/`, not in the integration suites.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
DOCKERFILE = ROOT / "Dockerfile"

IMAGE = "ghcr.io/porma-software/mcp-frankfurter"


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _dockerfile_text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


def _job_blocks(text: str) -> tuple[str, str]:
    """Split the `jobs:` section into (verify block, publish block), whatever their order."""
    jobs_text = "\n" + text.split("\njobs:\n", 1)[1]
    verify_start = jobs_text.index("\n  verify:")
    publish_start = jobs_text.index("\n  publish:")
    if verify_start < publish_start:
        return jobs_text[verify_start:publish_start], jobs_text[publish_start:]
    return jobs_text[verify_start:], jobs_text[publish_start:verify_start]


def test_release_workflow_exists() -> None:
    assert WORKFLOW.is_file()


def test_triggers_only_on_semver_tags() -> None:
    text = _workflow_text()
    on_block = re.search(r"^on:\n((?:[ \t]+.*\n?)+)", text, re.MULTILINE)
    assert on_block, "no top-level `on:` block found"
    body = on_block.group(1)
    assert "tags:" in body
    assert re.search(r'-\s*["\']v\*\.\*\.\*["\']', body)
    assert "branches" not in body
    assert "pull_request" not in body


def test_every_job_runs_on_ubuntu_latest() -> None:
    text = _workflow_text()
    jobs_block = text.split("\njobs:\n", 1)[1]
    job_names = re.findall(r"^  ([a-zA-Z0-9_-]+):\n", jobs_block, re.MULTILINE)
    assert set(job_names) == {"verify", "publish"}
    runs_on = re.findall(r"runs-on:\s*(\S+)", jobs_block)
    assert runs_on == ["ubuntu-latest"] * len(job_names)


def test_packages_write_only_in_publish_job_and_top_level_is_contents_read() -> None:
    text = _workflow_text()
    top_level = text.split("\njobs:\n", 1)[0]
    assert re.search(
        r"^permissions:\n(?:[ \t]+.*\n?)*?[ \t]+contents:\s*read\s*$", top_level, re.MULTILINE
    )
    assert "packages: write" not in top_level

    verify_block, publish_block = _job_blocks(text)
    assert "packages: write" not in verify_block
    assert "packages: write" in publish_block
    assert text.count("packages: write") == 1


def test_publish_needs_verify() -> None:
    _, publish_block = _job_blocks(_workflow_text())
    assert re.search(r"needs:\s*verify", publish_block)


def test_version_check_step_compares_tag_to_pyproject() -> None:
    verify_block, _ = _job_blocks(_workflow_text())
    assert "pyproject.toml" in verify_block
    assert "GITHUB_REF_NAME" in verify_block or "github.ref_name" in verify_block


def test_verify_job_runs_the_repo_gates() -> None:
    verify_block, _ = _job_blocks(_workflow_text())
    assert re.search(r"run:\s*make lint", verify_block)
    assert re.search(r"run:\s*make scenarios", verify_block)
    assert re.search(r"run:\s*make test", verify_block)


def test_image_name_is_exact_and_lowercase() -> None:
    text = _workflow_text()
    assert IMAGE in text
    assert "ghcr.io/Porma-Software" not in text


def test_login_uses_only_the_github_token_secret() -> None:
    text = _workflow_text()
    secrets_used = set(re.findall(r"secrets\.([A-Za-z0-9_]+)", text))
    assert secrets_used == {"GITHUB_TOKEN"}


def test_platforms_include_amd64_and_arm64() -> None:
    _, publish_block = _job_blocks(_workflow_text())
    platforms_match = re.search(r"platforms:\s*(.+)", publish_block)
    assert platforms_match
    platforms = platforms_match.group(1)
    assert "linux/amd64" in platforms
    assert "linux/arm64" in platforms


def test_dockerfile_carries_source_and_licence_labels() -> None:
    text = _dockerfile_text()
    assert (
        'org.opencontainers.image.source="https://github.com/Porma-Software/mcp-frankfurter"'
        in text
    )
    assert 'org.opencontainers.image.licenses="MIT"' in text
