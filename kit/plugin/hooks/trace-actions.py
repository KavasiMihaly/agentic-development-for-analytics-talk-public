"""Action trace, a PostToolUse and PostToolUseFailure hook: one JSON line per tool call in .trace/<session>.jsonl.

Records when, which tool, what it acted on (a command, a file, an MCP operation) and whether it succeeded.
Never records file contents, tool output, IDs, e-mail addresses, secrets or local paths. Never blocks: any
error is ignored. The .trace folder ignores itself in git. Read it with the show-trace skill.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
SECRET = re.compile(r"(?i)(bearer\s+|(?:password|secret|token|key)\s*[=:]\s*)\S+")
LOCAL = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"]*|/home/[^\s'\"]+|/Users/[^\s'\"]+")


def clean(text: str, project: Path) -> str:
    for root in (str(project), project.as_posix()):
        text = re.sub(re.escape(root) + r"[\\/]?", "", text, flags=re.I)
    text = SECRET.sub(lambda m: m.group(1) + "<secret>", EMAIL.sub("<upn>", GUID.sub("<id>", text)))
    return LOCAL.sub("<path>", text)[:200]


def where(path: str, project: Path) -> str:
    p = Path(path)
    try:
        return (p if p.is_absolute() else project / p).resolve().relative_to(project).as_posix()
    except (ValueError, OSError):
        return clean(p.name, project)


def what(tool: str, args: dict, project: Path) -> str:
    if tool in ("Bash", "PowerShell"):
        return clean(str(args.get("command") or "").strip().splitlines()[0] if args.get("command") else "", project)
    for key in ("file_path", "notebook_path"):
        if isinstance(args.get(key), str):
            return where(args[key], project)
    if tool in ("Grep", "Glob"):
        return clean(f"{args.get('pattern') or ''} {args.get('path') or args.get('glob') or ''}".strip(), project)
    if tool.startswith("mcp__"):
        request = args.get("request") if isinstance(args.get("request"), dict) else args
        return f"{tool.split('__')[-1]} {request.get('operation') or ''}".strip()
    for key in ("skill", "description", "url"):
        if isinstance(args.get(key), str):
            return clean(args[key][:80], project)
    return ""


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
        tool, args = str(event["tool_name"]), event.get("tool_input") or {}
        line = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), "tool": tool,
                "what": what(tool, args if isinstance(args, dict) else {}, project),
                "ok": event.get("hook_event_name") != "PostToolUseFailure", "ms": event.get("duration_ms")}
        session = re.sub(r"[^A-Za-z0-9_-]", "", str(event.get("session_id") or ""))[:64] or "session"
        folder = project / ".trace"
        folder.mkdir(exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8", newline="\n")
        with (folder / f"{session}.jsonl").open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - a trace must never stop the work
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
