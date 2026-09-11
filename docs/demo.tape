# Copyright (c) 2026 Nahúm Cueto López (Porma Software)
# SPDX-License-Identifier: MIT
# Renders docs/demo.gif from scripts/demo.py, a real MCP client over stdio hitting the real
# Frankfurter API -- see docs/vhs.Dockerfile for the exact render command. `uv sync` runs before
# this tape (outside the recording) so the terminal only ever shows the demo itself.

Output docs/demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1000
Set Height 560
Set Padding 20
Set Theme "Dracula"
Set TypingSpeed 40ms

Type "uv run python scripts/demo.py"
Enter
Sleep 15s
