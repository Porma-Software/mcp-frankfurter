# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Mutation gate: `mutmut run` must leave zero surviving mutants on `only_mutate`'s files.

`make mutation` runs mutmut and then this checker. A mutant that survives means the tests do not
pin the behaviour it changed: fix the test, not the gate. The only exception is a *provably
equivalent* mutant (the mutated code cannot behave differently); list it in EQUIVALENT_MUTANTS
with the reason, and the checker will still fail if any other mutant survives.

mutmut refuses to run natively on Windows: use WSL, a Linux box or CI. From Windows, copy the
project into a container (`ghcr.io/astral-sh/uv:python3.14-bookworm-slim`) and run `make mutation`
there; do not bind-mount the working tree, its `.venv` is not portable across platforms.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATS = ROOT / "mutants" / "mutmut-cicd-stats.json"

# mutant name -> why it cannot change observable behaviour. Reviewed like any other code.
# Empty for now: no Frankfurter tool/mapper logic exists yet in this scaffold slice (see
# docs/DECISIONS.md), so there is nothing yet to claim provably equivalent. Add an entry here
# only with a reason read from the mutant's own code (`uv run mutmut show <name>`), never as a
# way to silence a mutant nobody has looked at.
EQUIVALENT_MUTANTS: dict[str, str] = {}

# Verdicts that mean "the test suite did not prove anything about this mutant".
BAD_VERDICTS = ("survived", "suspicious", "timeout", "no_tests")
_RESULT_LINE = re.compile(r"^\s*(\S+):\s*(survived|suspicious|timeout|no tests)\s*$")


def _load_stats() -> dict[str, int]:
    if not STATS.is_file():
        print(f"FAIL: {STATS} is missing. Run `mutmut run && mutmut export-cicd-stats` first.")
        raise SystemExit(1)
    data: dict[str, int] = json.loads(STATS.read_text(encoding="utf-8"))
    return data


def _unproven_mutants() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-m", "mutmut", "results"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    names = []
    for line in result.stdout.splitlines():
        match = _RESULT_LINE.match(line)
        if match:
            names.append(match.group(1))
    return names


def main() -> int:
    stats = _load_stats()
    bad = sum(stats.get(key, 0) for key in BAD_VERDICTS)
    summary = (
        f"{stats.get('killed', 0)}/{stats.get('total', 0)} mutants killed, "
        f"{stats.get('survived', 0)} survived, {stats.get('suspicious', 0)} suspicious, "
        f"{stats.get('timeout', 0)} timed out, {stats.get('no_tests', 0)} untested"
    )
    if bad == 0:
        print(f"mutation gate passed: {summary}")
        return 0

    unexplained = [name for name in _unproven_mutants() if name not in EQUIVALENT_MUTANTS]
    if not unexplained and bad == len(EQUIVALENT_MUTANTS):
        print(f"mutation gate passed with {bad} documented equivalent mutants: {summary}")
        return 0

    print(f"mutation gate FAILED: {summary}")
    for name in unexplained:
        print(f"  - {name}: run `uv run mutmut show {name}` and add the missing assertion")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
