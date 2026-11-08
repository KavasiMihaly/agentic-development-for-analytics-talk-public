"""Trace check: every measure and every report page has a decision row, and every row's source resolves.

    python tools/check_trace.py                  # this repository
    python tools/check_trace.py --root <dir>

Decision rows live in docs/decisions/*.md, in a table with the columns ID | Decision | Source type | Source ref.
A row covers the measures and pages it names in backticks: measures by name, pages by name or title.
Sources resolve against the same file's Interview (Q1...) and Plan (numbered steps), the sections of AGENTS.md,
and docs/data-contract.yaml (its definition IDs, tables and table.Column). Rows with
source type "assumption" pass and are listed. Prints one JSON object.
Exit 0 = traced, 1 = a measure or page has no row or a source does not resolve.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from tmdl_lite import load_model  # noqa: E402

DECISIONS_DIR = Path("docs") / "decisions"
CONTRACT = Path("docs") / "data-contract.yaml"
SOURCE_TYPES = {"interview": "interview", "contract": "contract", "agents.md": "AGENTS.md", "agents": "AGENTS.md",
                "plan": "plan", "assumption": "assumption"}
HEADING = re.compile(r"^(#{2,3})\s+(.+?)\s*#*\s*$")
PLAN_STEP = re.compile(r"^\s*(\d+)[.)]\s+\S")
NAMED = re.compile(r"`([^`]+)`")
SEPARATOR = re.compile(r"^:?-{3,}:?$")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _sections(text: str) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = HEADING.match(line)
        if m and len(m.group(1)) == 2:
            current = m.group(2).strip().casefold()
            found.setdefault(current, [])
        elif current is not None:
            found[current].append(line)
    return found


def _tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    """Each markdown table in the lines as (header cells, body rows)."""
    tables, header, rows = [], None, []
    for line in lines + [""]:
        if line.lstrip().startswith("|"):
            cells = _cells(line)
            if header is None:
                header = [c.casefold() for c in cells]
            elif not all(SEPARATOR.match(c) for c in cells if c):
                rows.append(cells)
        elif header is not None:
            tables.append((header, rows))
            header, rows = None, []
    return tables


class Sources:
    """What a row may cite: AGENTS.md sections and the contract's IDs, tables and columns."""

    def __init__(self, root: Path):
        agents = root / "AGENTS.md"
        self.agents = None if not agents.is_file() else {
            m.group(2).strip().casefold() for m in map(HEADING.match, agents.read_text(encoding="utf-8").splitlines()) if m}
        self.contract_ids: set[str] | None = None
        self.contract_error = f"no {CONTRACT.as_posix()} to cite"
        if (root / CONTRACT).is_file():
            try:
                import yaml

                contract = yaml.safe_load((root / CONTRACT).read_text(encoding="utf-8")) or {}
            except ImportError:
                self.contract_error = f"PyYAML is needed to read {CONTRACT.as_posix()}"
                return
            ids = {str(d["id"]) for d in (contract.get("metrics") or {}).get("definitions", []) if d.get("id")}
            tables = contract.get("tables") or {}
            ids |= set(tables)
            ids |= {f"{t}.{c['name']}" for t, spec in tables.items() for c in (spec or {}).get("columns", [])}
            self.contract_ids = {i.casefold() for i in ids}
            self.definitions = sorted(str(d["id"]) for d in (contract.get("metrics") or {}).get("definitions", []) if d.get("id"))

    def why_not(self, kind: str, ref: str, answers: dict[str, str], steps: set[int]) -> str | None:
        if kind == "interview":
            m = re.fullmatch(r"(?i)(?:interview\s+)?Q(\d+)", ref)
            if not m:
                return f"'{ref}' is not an interview answer number (Q1, Q2, ...)"
            return None if f"Q{int(m.group(1))}" in answers else f"Q{int(m.group(1))} is not answered in this file's Interview"
        if kind == "plan":
            m = re.fullmatch(r"(?i)(?:plan\s+)?(?:step\s+)?(\d+)", ref)
            if not m:
                return f"'{ref}' is not a plan step number (step 1, step 2, ...)"
            return None if int(m.group(1)) in steps else f"step {m.group(1)} is not in this file's Plan"
        if kind == "AGENTS.md":
            section = re.sub(r"(?i)^agents\.md\s*", "", ref).lstrip("§ ").strip()
            if self.agents is None:
                return "there is no AGENTS.md to cite"
            return None if section.casefold() in self.agents else f"AGENTS.md has no section '{section}'"
        name = re.sub(r"(?i)^contract\s+", "", ref).strip("` ")
        if self.contract_ids is None:
            return self.contract_error
        return None if name.casefold() in self.contract_ids else (
            f"the contract has no '{name}' (definitions {', '.join(self.definitions)}, a table or table.Column)")


def decision_file(path: Path, root: Path, sources: Sources) -> dict:
    sections = _sections(path.read_text(encoding="utf-8"))
    answers = {}
    for _header, rows in _tables(sections.get("interview", [])):
        for cells in rows:
            if re.fullmatch(r"Q\d+", cells[0]) and cells[-1]:
                answers[f"Q{int(cells[0][1:])}"] = cells[-1]
    steps = {int(m.group(1)) for m in map(PLAN_STEP.match, sections.get("plan", [])) if m}
    name = _rel(path, root)
    out = {"file": name, "rows": [], "unresolved": [], "assumptions": [], "problems": []}
    table = next(((h, r) for h, r in _tables(sections.get("decisions", [])) if "source type" in h and "source ref" in h), None)
    if table is None:
        out["problems"].append({"file": name, "why": "no Decisions table (ID | Decision | Source type | Source ref)"})
        return out
    header, rows = table
    col = {key: header.index(key) for key in ("id", "decision", "source type", "source ref") if key in header}
    if len(col) < 4:
        out["problems"].append({"file": name, "why": "the Decisions table needs the columns ID, Decision, Source type, Source ref"})
        return out
    seen = set()
    for cells in rows:
        cells += [""] * (len(header) - len(cells))
        row_id, decision = cells[col["id"]], cells[col["decision"]]
        raw_type, raw_ref = cells[col["source type"]], cells[col["source ref"]]
        if row_id in seen:
            out["problems"].append({"file": name, "why": f"decision ID {row_id} is used twice"})
        seen.add(row_id)
        kind = SOURCE_TYPES.get(re.sub(r"\s+section$", "", raw_type.strip("` ").casefold()))
        out["rows"].append({"id": row_id, "names": [n.strip().casefold() for n in NAMED.findall(decision)]})
        problem = {"file": name, "id": row_id, "source_type": raw_type, "ref": raw_ref}
        if kind is None:
            out["unresolved"].append({**problem, "why": f"unknown source type '{raw_type}' (interview, contract, AGENTS.md, plan or assumption)"})
            continue
        if kind == "assumption":
            out["assumptions"].append({"file": name, "id": row_id, "decision": decision})
            continue
        refs = [r.strip() for r in re.split(r"[,;]", raw_ref) if r.strip()]
        whys = [w for w in (sources.why_not(kind, ref, answers, steps) for ref in refs) if w] if refs else ["no source ref"]
        if whys:
            out["unresolved"].append({**problem, "why": "; ".join(whys)})
    return out


def objects(root: Path, models: list[Path], reports: list[Path]) -> list[dict]:
    found = []
    for model in models:
        for table in load_model(model)["tables"].values():
            found += [{"kind": "measure", "name": m, "where": _rel(model, root), "keys": {m.casefold()}} for m in table.measures]
    for report in reports:
        for page_json in sorted((report / "definition" / "pages").glob("*/page.json")):
            page = json.loads(page_json.read_text(encoding="utf-8"))
            name, title = page.get("name") or page_json.parent.name, page.get("displayName") or ""
            found.append({"kind": "page", "name": name, "title": title, "where": _rel(report, root),
                          "keys": {name.casefold(), page_json.parent.name.casefold()} | ({title.casefold()} if title else set())})
    return found


def check(root: Path, models: list[Path] | None = None, reports: list[Path] | None = None) -> dict:
    root = Path(root).resolve()
    if models is None or reports is None:
        from gate import discover

        found_models, found_reports = discover(root)
        models = found_models if models is None else models
        reports = found_reports if reports is None else reports
    sources = Sources(root)
    files = [decision_file(p, root, sources) for p in sorted((root / DECISIONS_DIR).glob("*.md"))]
    named = {n for f in files for row in f["rows"] for n in row["names"]}
    built = objects(root, models, reports)
    untraced = [{k: v for k, v in o.items() if k != "keys"} for o in built if not o["keys"] & named]
    unresolved = [u for f in files for u in f["unresolved"]]
    problems = [p for f in files for p in f["problems"]]
    return {
        "measures": sum(o["kind"] == "measure" for o in built),
        "pages": sum(o["kind"] == "page" for o in built),
        "decision_files": [f["file"] for f in files],
        "rows": sum(len(f["rows"]) for f in files),
        "untraced": untraced,
        "unresolved": unresolved,
        "problems": problems,
        "assumptions": [a for f in files for a in f["assumptions"]],
        "ok": not untraced and not unresolved and not problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=HERE.parent)
    args = ap.parse_args(argv)
    result = check(args.root)
    print(json.dumps(result, indent=1))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
