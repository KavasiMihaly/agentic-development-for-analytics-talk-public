---
name: show-trace
description: Use when the person asks what the agent did in a session, for the action trace, or for a record of which tools ran and which files changed.
---

# Show the action trace

Run `python "${CLAUDE_SKILL_DIR}/show_trace.py"` for the latest session, or add `--list` or `--session <id>`.

Show the output as it is. The trace records actions, not contents, so it can say what was done and what failed. It cannot show what a file contained. Say so if the person asks for that.
