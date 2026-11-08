# Power BI gate (optional)

The checks a pull request must pass, run the same way on your machine and in CI. For projects saved as PBIP, with a TMDL model and a PBIR report.

| Step | What fails it |
|---|---|
| `ignores` | A best-practice rule suppressed with an annotation |
| `validate` | DAX or reference errors (only with the `te` CLI) |
| `relationships` | More than one active filter path between two tables, or a broken reference |
| `bpa` | The six rules in `bpa/team-rules.json` |
| `pbir` | Report files that break Microsoft's schemas, or fields the model doesn't have |
| `trace` | A measure or page with no decision row, or a row whose source doesn't exist |

## Add it

1. Copy `tools/`, `bpa/` and `.github/` from this folder to your project root.
2. Install what the gate calls, which you need to do yourself:

   ```bash
   pip install jsonschema PyYAML
   ```

   Install the free [Tabular Editor 2](https://github.com/TabularEditor/TabularEditor/releases). The gate looks in `TE2_CLI`, your `PATH`, then Program Files (x86). It's Windows-only, as is the workflow.
3. Run it from the project root:

   ```bash
   python tools/gate.py
   ```

Exit codes: 0 pass, 1 a check failed, 2 a tool or the rules file is missing.

Edit `bpa/team-rules.json` to match your standards. Rule 2 expects a measure called plain `Revenue`, `Sales` or `Total Revenue` to have a description starting with a definition ID, such as `R3 — Board revenue: …`.

## Decision trace

The `trace` step reads `docs/decisions/*.md` in the format the `requirements-interview` skill writes. Rows can cite the interview, the plan, a section of `AGENTS.md`, or a data contract at `docs/data-contract.yaml`. The contract is optional, but a row that cites one needs it:

```yaml
metrics:
  definitions:
    - id: R3
tables:
  fact_sales:
    columns:
      - name: Amount
```

## On pull requests

`.github/workflows/model-gate.yml` runs each step as its own check. It takes `tools/` and `bpa/` from the base branch, so a pull request can't weaken the gate that judges it. Tabular Editor 2 is downloaded at a pinned version and hash. To use the `te` CLI instead, set the repository variable `MODEL_GATE_TOOL` to `te`, or pass `--tool te` locally.
