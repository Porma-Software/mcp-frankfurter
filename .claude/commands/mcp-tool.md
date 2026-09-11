---
description: Scaffold a new MCP tool end to end (upstream method, tool, respx tests, README row); shows the plan and asks for confirmation before writing anything
argument-hint: <tool_name> [what it does]
---

Scaffold the tool `$ARGUMENTS` in this MCP server, following `.claude/skills/mcp-hexagonal/SKILL.md`
and `.claude/skills/mcp-testing/SKILL.md`.

## 1. Understand

- Read `src/mcp_frankfurter/mappers.py`, `upstream.py`, `server.py`, `tests/samples.py`,
  `docs/scenarios.md` and the README tools table.
- If `docs/specs/` holds a spec for this tool, follow it. Otherwise infer the upstream endpoint,
  arguments, ranges and output fields from the argument text and the existing code; ask one round
  of questions only for what is essential and unknown (endpoint, units, auth).

## 2. Plan, then stop and ask "Proceed?"

Present as a list, with the exact names:

- `mappers.py`: dataclass `<Record>`, `TypedDict <Output>`, `parse_<name>(payload) -> <Record>`
  (raise `ValueError` on a malformed shape), `to_<output>(record) -> <Output>` and its list form.
- `upstream.py`: method `async def <name>(...) -> list[<Record>]` calling `_get_json` then
  `parse_<name>` per item, wrapping its `ValueError` as `UpstreamError(str(exc))`.
- `config.py`, `.env.example`, README configuration table: new settings if any (`SecretStr` for
  secrets).
- `server.py`: `@mcp.tool() async def <tool_name>(...)` with
  `Annotated[..., Field(description=...)]` arguments, range validation with `ToolError` messages,
  `UpstreamError` wrapped as `ToolError("<service> unavailable: ...")`, `MAX_*` constants,
  returning `to_<output>s(records)`; `instructions=` update if the flow changes.
- `docs/scenarios.md`: one row per happy/failure path (new IDs).
- `tests/samples.py`: `<NAME>_URL`, `<NAME>_RESPONSE` (trimmed real payload), `EXPECTED_<NAME>`.
- `tests/unit/test_mappers.py`: parser + DTO mapping, field by field.
- `tests/integration/whitebox/` and `tests/integration/blackbox/`: one tagged test per new
  scenario ID in each; `TOOL_NAMES` in both suites' catalogue tests.
- README: tools table row.

Write nothing before the user confirms.

## 3. Write

Apply the plan in that order. Docstrings are written for the model (when to use, what it returns,
units, edge cases). Do not touch unrelated code.

## 4. Verify

Run `bash .claude/scripts/hex-check.sh` and report the tail of its output; also run
`uv run python scripts/check_scenarios.py`. Fix what fails, then list the files changed and what
is left for the user (capturing a real payload, a new secret in `.env`, running `make mutation`
in CI or a Linux container).
