# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Scenario catalogue checker: every ID in docs/scenarios.md must be covered, by a test that
actually runs, in both integration suites.

`make scenarios` (also runs in CI). Asks pytest to *collect* (no fixtures run, no network needed)
the white-box and black-box suites and reads each item's real `scenario` marker, instead of
grepping source text. That is deliberate: a decorator argument mentioned only in a comment or a
docstring does not produce a marker, and a test collected under `pytest.mark.skip` or
`pytest.mark.skipif` is reported separately so it cannot silently satisfy a catalogue row.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "docs" / "scenarios.md"
SUITES = {
    "white-box": ROOT / "tests" / "integration" / "whitebox",
    "black-box": ROOT / "tests" / "integration" / "blackbox",
}

# "| GEO-01 | ... |" rows of the catalogue tables.
_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]*-\d+)\s*\|", re.MULTILINE)


def catalogue_ids(path: Path) -> list[str]:
    return _ROW.findall(path.read_text(encoding="utf-8"))


class _ScenarioCollector:
    """pytest plugin: sorts collected items' `scenario` marker ids into run vs. skipped."""

    def __init__(self) -> None:
        self.covered: set[str] = set()
        self.skipped_only: dict[str, list[str]] = {}

    def pytest_collection_modifyitems(self, items: list[pytest.Item]) -> None:
        for item in items:
            marker = item.get_closest_marker("scenario")
            if marker is None:
                continue
            ids = [str(one) for one in marker.args]
            if item.get_closest_marker("skip") or item.get_closest_marker("skipif"):
                for one in ids:
                    self.skipped_only.setdefault(one, []).append(item.nodeid)
                continue
            self.covered.update(ids)
            for one in ids:
                # A later, non-skipped parametrization of the same id clears an earlier skip.
                self.skipped_only.pop(one, None)


def tagged_ids(directory: Path) -> tuple[set[str], dict[str, list[str]]]:
    collector = _ScenarioCollector()
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        exit_code = pytest.main(
            ["--collect-only", "-q", "-p", "no:cacheprovider", str(directory)],
            plugins=[collector],
        )
    if exit_code not in (pytest.ExitCode.OK, pytest.ExitCode.NO_TESTS_COLLECTED):
        print(f"FAIL: pytest could not collect {directory} (exit code {exit_code})")
        print(output.getvalue())
        raise SystemExit(1)
    return collector.covered, collector.skipped_only


def main() -> int:
    ids = catalogue_ids(CATALOGUE)
    if not ids:
        print(f"FAIL: no scenario rows found in {CATALOGUE}")
        return 1
    duplicates = sorted({one for one in ids if ids.count(one) > 1})
    catalogue = set(ids)
    problems: list[str] = [f"duplicate id in the catalogue: {one}" for one in duplicates]

    for name, directory in SUITES.items():
        if not directory.is_dir():
            problems.append(f"{name} suite directory is missing: {directory}")
            continue
        covered, skipped_only = tagged_ids(directory)
        for missing in sorted(catalogue - covered):
            if missing in skipped_only:
                where = ", ".join(skipped_only[missing])
                problems.append(f"{missing} is tagged only on skipped {name} test(s): {where}")
            else:
                problems.append(f"{missing} has no {name} test")
        for unknown in sorted(covered - catalogue):
            problems.append(f"{name} suite tags {unknown}, which is not in the catalogue")

    if problems:
        print(f"scenario check FAILED ({len(problems)} problems)")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"scenario check passed: {len(catalogue)} scenarios covered by both suites")
    return 0


if __name__ == "__main__":
    sys.exit(main())
