"""The model gate: the checks a pull request must pass, run the same way locally and in CI.

    python tools/gate.py                        # every step, with Tabular Editor 2
    python tools/gate.py --step bpa             # one step (repeatable)
    python tools/gate.py --tool te              # validate and BPA through the te CLI instead
    python tools/gate.py --root <dir>           # look for models and reports under <dir>

Steps, in order: ignores, validate, relationships, bpa, pbir, trace.
Models are the *.SemanticModel folders (with definition/) and reports the *.Report folders under the
root, outside .git/, .claude/ and tools/. Rules: bpa/team-rules.json. Decision log: docs/decisions/.
Exit 0 = pass, 1 = a check failed, 2 = a tool or the rules file is missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))

from check_bpa_ignores import find_ignores  # noqa: E402
from check_relationships import check as check_relationships  # noqa: E402
from check_trace import check as check_trace  # noqa: E402

STEPS = ("ignores", "validate", "relationships", "bpa", "pbir", "trace")
SKIP_DIRS = {".git", ".claude", "tools", "node_modules", ".venv", "__pycache__"}
CI = os.environ.get("GITHUB_ACTIONS") == "true"
LOCAL_PATH = re.compile(r"\b[A-Za-z]:[\\/][^\s'\"]*|/home/[^\s'\"]+|/Users/[^\s'\"]+")
TE2_VIOLATION = re.compile(r'^(?:::(error|warning|notice)::\s*)?(?P<obj>.+?) violates rule "(?P<rule>.*)"\s*$')


class ToolMissing(RuntimeError):
    pass


def scrub(text: str) -> str:
    return LOCAL_PATH.sub("<path>", str(text))


def te_cli() -> str | None:
    local = os.environ.get("LOCALAPPDATA")
    for candidate in (os.environ.get("TE_CLI"), shutil.which("te"),
                      str(Path(local) / "Programs" / "te" / "te.exe") if local else None):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def te2_cli() -> str | None:
    pf86 = os.environ.get("ProgramFiles(x86)")
    for candidate in (os.environ.get("TE2_CLI"), shutil.which("TabularEditor"),
                      str(Path(pf86) / "Tabular Editor" / "TabularEditor.exe") if pf86 else None):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def te_validate_command(te: str, definition: Path, ci: bool) -> list[str]:
    return [te, "validate", "-m", str(definition), "--output-format", "json", "--non-interactive"] + (
        ["--ci", "github"] if ci else [])


def te_bpa_command(te: str, definition: Path, rules: Path, ci: bool) -> list[str]:
    return [te, "bpa", "run", "-m", str(definition), "-r", str(rules), "--no-defaults", "--no-model-rules",
            "--fail-on", "error", "--output-format", "json", "--non-interactive"] + (["--ci", "github"] if ci else [])


def te2_bpa_command(te2: str, definition: Path, rules: Path) -> list[str]:
    return [te2, str(definition), "-AX", str(rules), "-G"]


def discover(root: Path) -> tuple[list[Path], list[Path]]:
    models, reports = [], []
    for current, dirs, _files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        path = Path(current)
        if path.name.endswith(".SemanticModel") and (path / "definition").is_dir():
            models.append(path)
        elif path.name.endswith(".Report") and (path / "definition.pbir").is_file():
            reports.append(path)
    return models, reports


def run(cmd: list[str]) -> tuple[int, dict | None, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = proc.stdout
    data = None
    if "{" in out:
        try:
            data = json.loads(out[out.index("{"):])
        except ValueError:
            data = None
    if CI and proc.stderr:
        sys.stderr.write("".join(line + "\n" for line in proc.stderr.splitlines() if line.startswith("::")))
    return proc.returncode, data, proc.stderr


class Gate:
    def __init__(self, root: Path, rules: Path, tool: str):
        self.root, self.rules, self.tool = root, rules, tool
        self.models, self.reports = discover(root)
        self.failed: list[str] = []

    def name(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.name

    def say(self, step: str, verdict: str, subject: str, detail: str = "") -> None:
        print(f"[{step}] {verdict} {subject}" + (f": {detail}" if detail else ""), flush=True)
        if verdict == "NOTE" and CI:
            print(f"::notice title=model gate - {step}::{subject}: {detail}", file=sys.stderr, flush=True)
        if verdict == "FAIL":
            if CI:
                print(f"::error title=model gate - {step}::{subject}: {detail}", file=sys.stderr, flush=True)
            if step not in self.failed:
                self.failed.append(step)

    def ignores(self) -> None:
        for model in self.models:
            hits = find_ignores(model)
            if hits:
                self.say("ignores", "FAIL", self.name(model), "BestPracticeAnalyzer_IgnoreRules at " + ", ".join(hits)
                         + " - the gate does not accept suppressed rules")
            else:
                self.say("ignores", "PASS", self.name(model))

    def validate(self) -> None:
        if self.tool == "te2":
            for model in self.models:
                self.say("validate", "SKIP", self.name(model), "TabularEditor.exe has no offline DAX validation; the bpa step loads the model")
            return
        te = te_cli()
        if te is None and self.models:
            raise ToolMissing("te CLI not found (TE_CLI, PATH or %LOCALAPPDATA%/Programs/te)")
        for model in self.models:
            code, data, err = run(te_validate_command(te, model / "definition", CI))
            if data is None:
                self.say("validate", "FAIL", self.name(model), "te could not load the model: " + scrub(err.strip().splitlines()[-1] if err.strip() else f"exit {code}"))
                continue
            errors = [f for f in data.get("findings", []) if f.get("severity") == "error"]
            if code != 0 or errors or data.get("valid") is not True:
                detail = "; ".join(f"{f.get('code')} {f.get('objectPath') or f.get('object')}: {scrub(f.get('message', ''))[:200]}" for f in errors)
                self.say("validate", "FAIL", self.name(model), detail or f"exit {code}")
            else:
                s = data.get("summary", {})
                self.say("validate", "PASS", self.name(model), f"{s.get('errors', 0)} errors, {s.get('warnings', 0)} warnings")

    def relationships(self) -> None:
        for model in self.models:
            result = check_relationships(model)
            if result["ok"]:
                self.say("relationships", "PASS", self.name(model), f"{result['active']} active of {result['relationships']}, one path between any two tables")
                continue
            parts = [f"{a['from']} -> {a['to']} has {a['paths']} active paths" for a in result["ambiguous"]]
            parts += [f"{b['relationship']} refers to missing {b['missing']}" for b in result["broken"]]
            self.say("relationships", "FAIL", self.name(model), "; ".join(parts))

    def bpa(self) -> None:
        if not self.models:
            return
        if self.tool == "te2":
            te2 = te2_cli()
            if te2 is None:
                raise ToolMissing("TabularEditor.exe not found (TE2_CLI, PATH or Program Files (x86))")
            for model in self.models:
                proc = subprocess.run(te2_bpa_command(te2, model / "definition", self.rules), capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
                found = [m for m in map(TE2_VIOLATION.match, proc.stdout.splitlines()) if m]
                errors = [f"{m['rule']} - {m['obj']}" for m in found if m.group(1) != "warning"]
                warnings = [f"{m['rule']} - {m['obj']}" for m in found if m.group(1) == "warning"]
                for w in warnings:
                    self.say("bpa", "WARN", self.name(model), w)
                if proc.returncode != 0:
                    loading = [scrub(line) for line in proc.stdout.splitlines() if "Error" in line and "violates" not in line]
                    self.say("bpa", "FAIL", self.name(model), "; ".join(errors + loading) or f"exit {proc.returncode}")
                else:
                    self.say("bpa", "PASS", self.name(model), f"team rules, {len(warnings)} warnings")
            return
        te = te_cli()
        if te is None:
            raise ToolMissing("te CLI not found (TE_CLI, PATH or %LOCALAPPDATA%/Programs/te)")
        for model in self.models:
            code, data, err = run(te_bpa_command(te, model / "definition", self.rules, CI))
            if data is None:
                self.say("bpa", "FAIL", self.name(model), "te could not run the rules: " + scrub(err.strip().splitlines()[-1] if err.strip() else f"exit {code}"))
                continue
            for f in data.get("findings", []):
                line = f"{f.get('code')} {f.get('objectPath') or f.get('object')} - {f.get('ruleName') or f.get('message', '')}"
                if f.get("severity") != "error":
                    self.say("bpa", "WARN", self.name(model), line)
            errors = [f for f in data.get("findings", []) if f.get("severity") == "error"]
            if code != 0 or errors or data.get("ruleErrors"):
                detail = "; ".join(f"{f.get('code')} {f.get('objectPath') or f.get('object')} - {f.get('ruleName') or f.get('message', '')}" for f in errors)
                self.say("bpa", "FAIL", self.name(model), detail or f"exit {code}, rule errors {data.get('ruleErrors')}")
            else:
                self.say("bpa", "PASS", self.name(model), f"{data.get('rulesEvaluated')} team rules, {data['summary'].get('warnings', 0)} warnings")

    def pbir(self) -> None:
        from validate_pbir import validate as validate_report

        for report in self.reports:
            try:
                rep, counts, _versions, _meta = validate_report(report.resolve(), None, HERE / "schemas")
            except Exception as exc:  # noqa: BLE001
                self.say("pbir", "FAIL", self.name(report), f"validator crashed: {type(exc).__name__}: {scrub(exc)}")
                continue
            findings = rep.errors + rep.warnings
            if findings:
                self.say("pbir", "FAIL", self.name(report), "; ".join(f"{f['code']} {f['file']}: {f['message']}" for f in findings[:12])
                         + (f" (+{len(findings) - 12} more)" if len(findings) > 12 else ""))
            else:
                self.say("pbir", "PASS", self.name(report), f"{counts['pages']} pages, {counts['visuals']} visuals, {counts['field_refs']} field references")

    def trace(self) -> None:
        result = check_trace(self.root, self.models, self.reports)
        for p in result["problems"]:
            self.say("trace", "FAIL", p["file"], p["why"])
        for u in result["untraced"]:
            title = f' ("{u["title"]}")' if u.get("title") else ""
            self.say("trace", "FAIL", u["where"], f"{u['kind']} `{u['name']}`{title} has no decision row in docs/decisions/")
        for u in result["unresolved"]:
            self.say("trace", "FAIL", f"{u['file']} {u['id']}", f"source {u['source_type']} '{u['ref']}' does not resolve: {u['why']}")
        for a in result["assumptions"]:
            self.say("trace", "NOTE", f"{a['file']} {a['id']}", f"assumption, not agreed: {a['decision']}")
        if result["ok"]:
            self.say("trace", "PASS", "docs/decisions/", f"{result['measures']} measures and {result['pages']} pages traced "
                     f"by {result['rows']} rows in {len(result['decision_files'])} file(s), {len(result['assumptions'])} assumption(s)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", action="append", choices=STEPS, help="run only this step (repeatable)")
    ap.add_argument("--tool", choices=("te", "te2"), default=os.environ.get("GATE_TOOL") or "te2")
    ap.add_argument("--rules", type=Path, default=REPO / "bpa" / "team-rules.json")
    ap.add_argument("--root", type=Path, default=REPO)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not args.rules.is_file():
        print("gate: rules file not found: bpa/team-rules.json")
        return 2
    gate = Gate(args.root.resolve(), args.rules.resolve(), args.tool)
    print(f"gate: {len(gate.models)} model(s), {len(gate.reports)} report(s), tool {args.tool}: "
          + ", ".join(gate.name(p) for p in gate.models + gate.reports))
    try:
        for step in [s for s in STEPS if not args.step or s in args.step]:
            getattr(gate, step)()
    except ToolMissing as exc:
        print(f"gate: ERROR {exc}")
        return 2
    print("gate: " + (f"FAIL ({', '.join(gate.failed)})" if gate.failed else "PASS"))
    return 1 if gate.failed else 0


if __name__ == "__main__":
    sys.exit(main())
