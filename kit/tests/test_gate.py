"""Tests for the optional Power BI gate, on a small synthetic model. Standard library only.

The PBIR and BPA steps need jsonschema and Tabular Editor, so they are not run here.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

GATE = Path(__file__).resolve().parents[1] / "powerbi-gate"
TOOLS = GATE / "tools"

SALES = """table Sales
\tmeasure 'Net Revenue' = SUM(Sales[Amount])
\t\tformatString: 0

\tcolumn CustomerKey
\t\tdataType: int64

\tcolumn RegionKey
\t\tdataType: int64

\tcolumn Amount
\t\tdataType: decimal
"""
CUSTOMER = "table Customer\n\tcolumn CustomerKey\n\t\tdataType: int64\n\n\tcolumn RegionKey\n\t\tdataType: int64\n"
REGION = "table Region\n\tcolumn RegionKey\n\t\tdataType: int64\n"
ONE_PATH = """relationship s_c
\tfromColumn: Sales.CustomerKey
\ttoColumn: Customer.CustomerKey

relationship c_r
\tfromColumn: Customer.RegionKey
\ttoColumn: Region.RegionKey
"""
SECOND_PATH = """
relationship s_r
\tfromColumn: Sales.RegionKey
\ttoColumn: Region.RegionKey
"""
DECISIONS = """# Decisions

## Interview

| Q | Question | Answer |
|---|---|---|
| Q1 | Which definition? | Net |

## Plan

1. Build the measure

## Decisions

| ID | Decision | Source type | Source ref |
|---|---|---|---|
| D1 | `Net Revenue` is the headline | {kind} | {ref} |
"""


def run_gate(root, *steps):
    args = [arg for step in steps for arg in ("--step", step)]
    return subprocess.run([sys.executable, str(TOOLS / "gate.py"), "--root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8")


class GateCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.definition = self.root / "powerbi" / "Sample.SemanticModel" / "definition"
        (self.definition / "tables").mkdir(parents=True)
        for name, body in (("Sales", SALES), ("Customer", CUSTOMER), ("Region", REGION)):
            (self.definition / "tables" / f"{name}.tmdl").write_text(body, encoding="utf-8")
        self.relationships(ONE_PATH)

    def relationships(self, text):
        (self.definition / "relationships.tmdl").write_text(text, encoding="utf-8")

    def decisions(self, kind="interview", ref="Q1"):
        folder = self.root / "docs" / "decisions"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "request.md").write_text(DECISIONS.format(kind=kind, ref=ref), encoding="utf-8")


class Relationships(GateCase):
    def test_one_path_passes(self):
        done = run_gate(self.root, "relationships")
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_second_active_path_fails_and_names_the_tables(self):
        self.relationships(ONE_PATH + SECOND_PATH)
        done = run_gate(self.root, "relationships")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("Region -> Sales has 2 active paths", done.stdout)

    def test_inactive_second_path_passes(self):
        self.relationships(ONE_PATH + SECOND_PATH + "\tisActive: false\n")
        self.assertEqual(run_gate(self.root, "relationships").returncode, 0)

    def test_missing_column_fails(self):
        self.relationships(ONE_PATH.replace("Sales.CustomerKey", "Sales.Nope"))
        self.assertEqual(run_gate(self.root, "relationships").returncode, 1)


class Ignores(GateCase):
    def test_suppressed_rule_fails(self):
        path = self.definition / "tables" / "Region.tmdl"
        path.write_text(REGION + "\tannotation BestPracticeAnalyzer_IgnoreRules = x\n", encoding="utf-8")
        done = run_gate(self.root, "ignores")
        self.assertEqual(done.returncode, 1, done.stdout)


class Trace(GateCase):
    def test_traced_measure_passes(self):
        self.decisions()
        self.assertEqual(run_gate(self.root, "trace").returncode, 0)

    def test_untraced_measure_fails_and_names_it(self):
        done = run_gate(self.root, "trace")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("Net Revenue", done.stdout)

    def test_source_that_does_not_exist_fails(self):
        self.decisions("plan", "step 9")
        done = run_gate(self.root, "trace")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("step 9", done.stdout)

    def test_assumption_passes_and_is_listed(self):
        self.decisions("assumption", "not agreed")
        done = run_gate(self.root, "trace")
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn("assumption, not agreed", done.stdout)

    def test_agents_section_resolves(self):
        (self.root / "AGENTS.md").write_text("# Team\n\n## Report standards\n", encoding="utf-8")
        self.decisions("AGENTS.md", "§Report standards")
        self.assertEqual(run_gate(self.root, "trace").returncode, 0)

    def test_contract_citation_without_contract_fails(self):
        self.decisions("contract", "NET")
        done = run_gate(self.root, "trace")
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn("data-contract.yaml", done.stdout)


class Packaging(unittest.TestCase):
    def setUp(self):
        self.rules = json.loads((GATE / "bpa" / "team-rules.json").read_text(encoding="utf-8"))

    def test_six_generic_rules(self):
        self.assertEqual(len(self.rules), 6)
        self.assertTrue(all(rule["ID"].startswith("TEAM_") for rule in self.rules))

    def test_revenue_rule_accepts_any_definition_id(self):
        expression = next(r for r in self.rules if r["ID"].startswith("TEAM_02"))["Expression"]
        self.assertNotIn("R[1-4]", expression)

    def test_gate_defaults_to_the_free_tool(self):
        self.assertIn('or "te2"', (TOOLS / "gate.py").read_text(encoding="utf-8"))
        self.assertIn("|| 'te2'", (GATE / ".github" / "workflows" / "model-gate.yml").read_text(encoding="utf-8"))

    def test_nothing_from_the_demo(self):
        for path in GATE.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".json", ".yml"}:
                text = path.read_text(encoding="utf-8").casefold()
                for word in ("halden", "gold-contract", "fact_gl_monthly"):
                    self.assertNotIn(word, text, f"{path.name}: {word}")


if __name__ == "__main__":
    unittest.main()
