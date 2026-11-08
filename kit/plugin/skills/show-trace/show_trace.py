"""Show the action trace: what the agent did, in order, from .trace/<session>.jsonl in the project.

    python show_trace.py                   # the latest session
    python show_trace.py --session <id>
    python show_trace.py --list            # the sessions on record

The trace holds one line per tool call, with no file contents or tool output. Prints each call (time, tool, what
it acted on, failures marked), then the files written or edited. Exit 0, or 1 when there is no trace.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

WRITES = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


def sessions(root: Path) -> list[Path]:
    return sorted((root / ".trace").glob("*.jsonl"), key=lambda p: p.stat().st_mtime)


def read(path: Path) -> list[dict]:
    calls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            calls.append(json.loads(line))
        except ValueError:
            continue
    return calls


def receipt(name: str, calls: list[dict]) -> str:
    failed = sum(not c.get("ok", True) for c in calls)
    times = [str(c.get("at", ""))[11:19] for c in calls]
    span = f", {times[0]} to {times[-1]}" if times and times[0] else ""
    out = [f"Action trace: session {name}, {len(calls)} tool calls, {failed} failed{span}", ""]
    for c, t in zip(calls, times):
        tool = "MCP" if str(c.get("tool", "")).startswith("mcp__") else c.get("tool", "?")
        out.append(f"  {t:8}  {tool:<11} {c.get('what', '')}" + ("   FAILED" if not c.get("ok", True) else ""))
    changed = list(dict.fromkeys(c.get("what", "") for c in calls if c.get("tool") in WRITES and c.get("ok", True)))
    out += ["", f"Files written or edited ({len(changed)}): " + (", ".join(changed) if changed else "none")]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=Path(os.environ.get("CLAUDE_PROJECT_DIR") or "."))
    ap.add_argument("--session", help="a session id (the file name in .trace/ without .jsonl)")
    ap.add_argument("--list", action="store_true", help="list the sessions on record")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    found = sessions(args.root)
    if not found:
        print("No action trace yet (.trace/ is empty).")
        return 1
    if args.list:
        for p in found:
            print(f"{p.stem}  {len(read(p))} tool calls")
        return 0
    path = next((p for p in found if p.stem == args.session), None) if args.session else found[-1]
    if path is None:
        print(f"No trace for session {args.session}.")
        return 1
    print(receipt(path.stem, read(path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
