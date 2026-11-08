"""Data boundary, a PreToolUse hook: the agent checks numbers with tools that return verdicts, never data rows.

Denies Read and Grep on data files (Parquet, CSV, TSV, plus any in the project's config); Bash and PowerShell
commands, and the Python scripts and query files they use, that read data files, run ad-hoc DAX, use a SQL client
or copy lakehouse files; and MCP calls that run DAX. Check tools are trusted at their own paths.

Optional project config, .claude/data-boundary.json:
    {"check_tools": ["scripts/my_check.py"], "data_extensions": ["xlsx"]}

Fails closed: a malformed event, a broken config or an error in this hook is a deny.
It reads what a command says, so it is a seatbelt, not a vault. For real customer data, the real boundary is what
the agent's identity is allowed to read.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DATA_EXTENSIONS = ("parquet", "csv", "tsv")
CHECK_TOOLS = {"tools/gate.py", "tools/check_trace.py", "tools/check_relationships.py", "tools/check_bpa_ignores.py",
               "tools/validate_pbir.py"}
CONFIG = Path(".claude") / "data-boundary.json"
QUERY_RULES = (
    ("runs ad-hoc DAX", re.compile(r"\bEVALUATE\b|executeQueries|EvaluateDax|ExecuteDax"
                                   r"|\bte(?:\.exe)?\s+(?:query|interactive)\b", re.I)),
    ("reads data rows", re.compile(r"\b(sqlcmd|Invoke-Sqlcmd|pyodbc|pymssql|sqlalchemy)\b|onelake\.dfs\.fabric"
                                   r"|\bfab\s+(cp|copy|mv|move|cat|export|bulk-export)\b.*\.Lakehouse", re.I)),
)
SCRIPT = re.compile(r"""\b(?:python3?|py)(?:\.exe)?\s+(?:-[A-Za-z]\S*\s+)*(?:"([^"]+?\.py)"|'([^']+?\.py)'|([^\s"';&|]+?\.py))(?![\w.])""", re.I)
QUERY_FILE = re.compile(r"""(?:"([^"]+?\.(?:dax|csx?|sql))"|'([^']+?\.(?:dax|csx?|sql))'|([^\s"';&|<>]+?\.(?:dax|csx?|sql)))(?![\w.])""", re.I)
INSTEAD = "Check numbers with a tool that returns a verdict, such as a reconciliation check or the project's gate."


class Boundary:
    def __init__(self, project: Path):
        self.project = project
        self.check_tools = set(CHECK_TOOLS)
        extensions = list(DATA_EXTENSIONS)
        config = project / CONFIG
        if config.is_file():
            settings = json.loads(config.read_text(encoding="utf-8"))
            self.check_tools |= {str(t).replace("\\", "/") for t in settings.get("check_tools", [])}
            extensions += [str(e).lstrip(".").casefold() for e in settings.get("data_extensions", [])]
        self.extensions = extensions
        self.data_file = re.compile(r"\.(" + "|".join(map(re.escape, extensions)) + r")\b", re.I)
        self.rules = (("reads a data file", self.data_file), *QUERY_RULES)

    def shown(self, path: str | Path) -> str:
        """A path fit for the screen: relative to the project, or only the file name."""
        p = Path(str(path).replace("\\", "/"))
        try:
            return (p if p.is_absolute() else self.project / p).resolve().relative_to(self.project).as_posix()
        except (ValueError, OSError):
            return p.name

    def is_check_tool(self, script: Path) -> bool:
        return script.is_relative_to(self.project) and script.relative_to(self.project).as_posix() in self.check_tools

    def why_denied(self, tool: str, args: dict, cwd: Path) -> str | None:
        if tool in ("Read", "Grep"):
            targets = [text(args, k) for k in ("file_path", "path", "glob")]
            if any(self.data_file.search(t) for t in targets) or text(args, "type").casefold() in self.extensions:
                return f"{tool} of {self.shown(next((t for t in targets if t), '*'))} reads a data file"
            return None
        if tool in ("Bash", "PowerShell"):
            return self.why_command_denied(text(args, "command", required=True), cwd)
        if tool.startswith("mcp__"):
            if "dax_query" in tool:
                return f"{tool.split('__')[-1]} runs ad-hoc DAX"
            body = json.dumps(args)
            for reason, rule in self.rules:
                if rule.search(body):
                    return f"this {tool.split('__')[-1]} call {reason}"
        return None

    def why_command_denied(self, command: str, cwd: Path) -> str | None:
        files = list(scripts(command, cwd))
        if len(files) == 1 and self.is_check_tool(files[0]) and not re.search(r"[;&|<>`\n]|\$\(", command):
            return None  # one plain call of a listed check tool, which may name data files itself
        for reason, rule in self.rules:
            if rule.search(command):
                return f"this command {reason}"
        for script in files:
            if script.is_file() and not self.is_check_tool(script):
                body = script.read_text(encoding="utf-8", errors="replace")
                for reason, rule in self.rules:
                    if rule.search(body):
                        return f"{self.shown(script)} {reason}"
        return None


def text(args: dict, key: str, required: bool = False) -> str:
    value = args.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"tool_input.{key} is not text")
    return value


def scripts(command: str, cwd: Path):
    """Python scripts the command runs, and the query or C# script files it names."""
    for m in (*SCRIPT.finditer(command), *QUERY_FILE.finditer(command)):
        raw = next(g for g in m.groups() if g).replace("\\", "/")
        yield (cwd / raw).resolve()


def main() -> int:
    try:
        event = json.loads(sys.stdin.read())
        tool, args = event["tool_name"], event["tool_input"]
        if not isinstance(tool, str) or not isinstance(args, dict):
            raise ValueError("tool_name or tool_input has the wrong type")
        project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or event.get("cwd") or ".").resolve()
        reason = Boundary(project).why_denied(tool, args, Path(event.get("cwd") or project))
    except Exception as exc:  # noqa: BLE001 - fail closed
        reason = f"the call could not be checked ({type(exc).__name__})"
    if reason is None:
        return 0
    message = f"Denied by the data boundary: {reason}. {INSTEAD}"
    try:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                 "permissionDecisionReason": message}}))
        return 0
    except Exception:  # noqa: BLE001 - exit 2 blocks the call too
        sys.stderr.write(message)
        return 2


if __name__ == "__main__":
    sys.exit(main())
