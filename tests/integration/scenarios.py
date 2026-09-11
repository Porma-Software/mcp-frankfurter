# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Scenario tags shared by both integration suites.

`docs/scenarios.md` is the catalogue; `make scenarios` (scripts/check_scenarios.py) fails when
one of its IDs is missing from the white-box or from the black-box suite.
"""

from __future__ import annotations

import pytest


def scenario(*ids: str) -> pytest.MarkDecorator:
    """Tag a test with the catalogue IDs it covers, e.g. `@scenario("AUTH-01")`."""
    return pytest.mark.scenario(*ids)
