"""Tests for the plugin's hooks. Standard library only: python -m unittest discover -s kit/tests"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "plugin"
BOUNDARY = PLUGIN / "hooks" / "no-data-rows.py"
TRACE = PLUGIN / "hooks" / "trace-actions.py"
SHOW = PLUGIN / "skills" / "show-trace" / "show_trace.py"


class ProjectCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()

    def hook(self, script, payload):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.project)}
        return subprocess.run([sys.executable, str(script)], input=raw, capture_output=True, text=True, env=env)

    def decide(self, tool, args):
        done = self.hook(BOUNDARY, {"tool_name": tool, "tool_input": args, "cwd": str(self.project)})
        self.assertEqual(done.returncode, 0, done.stderr)
        if not done.stdout.strip():
            return None
        output = json.loads(done.stdout)["hookSpecificOutput"]
        self.assertEqual(output["permissionDecision"], "deny")
        return output["permissionDecisionReason"]


class DataBoundary(ProjectCase):
    def test_read_of_data_files_is_denied(self):
        for name in ("sales.csv", "sales.parquet", "sales.tsv", "SALES.CSV"):
            self.assertIn("data file", self.decide("Read", {"file_path": name}), name)

    def test_grep_of_data_files_is_denied(self):
        self.assertIsNotNone(self.decide("Grep", {"pattern": "x", "glob": "*.csv"}))
        self.assertIsNotNone(self.decide("Grep", {"pattern": "x", "type": "csv"}))

    def test_ordinary_read_is_allowed(self):
        self.assertIsNone(self.decide("Read", {"file_path": "AGENTS.md"}))

    def test_ad_hoc_queries_are_denied(self):
        for command in ('te query "EVALUATE Sales"', "sqlcmd -S server -Q x", "python -c 'import pyodbc'", "cat sales.csv"):
            self.assertIsNotNone(self.decide("Bash", {"command": command}), command)
            self.assertIsNotNone(self.decide("PowerShell", {"command": command}), command)

    def test_ordinary_command_is_allowed(self):
        self.assertIsNone(self.decide("Bash", {"command": "git status"}))

    def test_script_that_reads_rows_is_denied(self):
        (self.project / "peek.py").write_text("import pyodbc\n", encoding="utf-8")
        self.assertIn("peek.py", self.decide("Bash", {"command": "python peek.py"}))

    def test_listed_check_tool_is_allowed(self):
        tools = self.project / "tools"
        tools.mkdir()
        (tools / "gate.py").write_text("# looks for EVALUATE and .csv\n", encoding="utf-8")
        self.assertIsNone(self.decide("Bash", {"command": "python tools/gate.py"}))

    def test_tool_listed_in_project_config_is_allowed(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "data-boundary.json").write_text('{"check_tools": ["scripts/recon.py"]}', encoding="utf-8")
        (self.project / "scripts").mkdir()
        (self.project / "scripts" / "recon.py").write_text("import pyodbc\n", encoding="utf-8")
        self.assertIsNone(self.decide("Bash", {"command": "python scripts/recon.py"}))

    def test_extra_extension_from_config_is_denied(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "data-boundary.json").write_text('{"data_extensions": ["xlsx"]}', encoding="utf-8")
        self.assertIsNotNone(self.decide("Read", {"file_path": "book.xlsx"}))
        self.assertIsNotNone(self.decide("Read", {"file_path": "still.csv"}))

    def test_broken_config_fails_closed(self):
        (self.project / ".claude").mkdir()
        (self.project / ".claude" / "data-boundary.json").write_text("{not json", encoding="utf-8")
        self.assertIn("could not be checked", self.decide("Read", {"file_path": "AGENTS.md"}))

    def test_mcp_query_tool_is_denied(self):
        self.assertIsNotNone(self.decide("mcp__powerbi-modeling__dax_query_operations", {"request": {}}))
        self.assertIsNotNone(self.decide("mcp__other__run", {"query": "EVALUATE Sales"}))

    def test_malformed_event_fails_closed(self):
        done = self.hook(BOUNDARY, "not json")
        self.assertIn("could not be checked", json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"])

    def test_message_names_nothing_from_the_demo(self):
        self.assertNotIn("Halden", self.decide("Read", {"file_path": "a.csv"}))


class ActionTrace(ProjectCase):
    def event(self, command="git status", **extra):
        return {"tool_name": "Bash", "tool_input": {"command": command}, "session_id": "abc",
                "hook_event_name": "PostToolUse", "cwd": str(self.project), **extra}

    def lines(self):
        text = (self.project / ".trace" / "abc.jsonl").read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]

    def test_records_the_action(self):
        self.hook(TRACE, self.event())
        line = self.lines()[0]
        self.assertEqual((line["tool"], line["what"], line["ok"]), ("Bash", "git status", True))

    def test_failure_is_marked(self):
        self.hook(TRACE, self.event(hook_event_name="PostToolUseFailure"))
        self.assertFalse(self.lines()[0]["ok"])

    def test_private_values_are_scrubbed(self):
        guid = "12345678-1234-1234-1234-123456789abc"
        self.hook(TRACE, self.event(f"run {guid} me@example.com token=hunter2 C:\\Users\\me\\x"))
        what = self.lines()[0]["what"]
        for secret in (guid, "me@example.com", "hunter2", "Users"):
            self.assertNotIn(secret, what)

    def test_trace_folder_ignores_itself_in_git(self):
        self.hook(TRACE, self.event())
        self.assertEqual((self.project / ".trace" / ".gitignore").read_text(encoding="utf-8").strip(), "*")

    def test_never_blocks(self):
        done = self.hook(TRACE, "not json")
        self.assertEqual((done.returncode, done.stdout), (0, ""))

    def test_show_trace_reads_the_project(self):
        self.hook(TRACE, self.event())
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.project)}
        done = subprocess.run([sys.executable, str(SHOW)], capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("git status", done.stdout)


class Packaging(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]

    def commands(self):
        return [h for groups in self.config.values() for group in groups for h in group["hooks"]]

    def test_every_hook_script_exists(self):
        for hook in self.commands():
            self.assertEqual(hook["command"], "python")
            self.assertTrue(hook["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}/hooks/"), hook["args"][0])
            name = hook["args"][0].rsplit("/", 1)[1]
            self.assertTrue((PLUGIN / "hooks" / name).is_file(), name)

    def test_boundary_hook_blocks_when_it_cannot_run(self):
        groups = self.config["PreToolUse"]
        self.assertTrue(all(h["onFailure"] == "block" for g in groups for h in g["hooks"]))

    def test_plugin_files_name_nothing_from_the_demo(self):
        for path in PLUGIN.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".json"}:
                self.assertNotIn("halden", path.read_text(encoding="utf-8").casefold(), path.name)


if __name__ == "__main__":
    unittest.main()
