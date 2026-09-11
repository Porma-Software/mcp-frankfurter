# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
"""Pure mapping functions and typed records at every boundary this server crosses.

Empty for now: no Frankfurter record or DTO type exists yet. The next development slice adds the
frozen-dataclass records, the `TypedDict` tool DTOs and the pure `parse_*`/`to_*` functions
between them here, exactly as `.claude/skills/mcp-hexagonal/SKILL.md` describes; `server.py` and
`upstream.py` will keep never building one of those literals themselves.

No `mcp` or `httpx` import here, so every function this module gains stays unit-testable on plain
data, field by field, without a mocked HTTP call or a running server.
"""
