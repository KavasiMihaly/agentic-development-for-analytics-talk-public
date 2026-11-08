# Decisions: board revenue report

An illustration for a fictional company. It follows the [decision log format](../../plugin/skills/requirements-interview/decision-log.md).

Request: "Build me a sales report from the Halden gold lakehouse"
Agreed: "yes" to the plan below

## Interview

| Q | Question | Answer |
|---|---|---|
| Q1 | Who is it for, and what decision does it support? | The board: is revenue growing |
| Q2 | Which definition of the main measure? | R3, board revenue |
| Q3 | Which meaning of any other ambiguous term? | Sales territory |
| Q4 | Which calendar? | Fiscal, July to June (default, in the agreed plan) |
| Q5 | Which period, and compared with what? | Latest complete fiscal year against the one before, by month |

## Plan

1. Page 1 — Is board revenue growing? (R3): card, line by month, matrix by sales territory
2. Checks: gate, then reconcile R3 with the ledger

## Decisions

| ID | Decision | Source type | Source ref |
|---|---|---|---|
| D1 | The headline figure is `Board Revenue (R3)` | interview | Q2 |
| D2 | `Board Revenue (R3)` is net of credits and accrued rebates | contract | R3 |
| D3 | Territory on page `board-revenue` is sales territory, labelled as such | interview | Q3 |
| D4 | Time is the fiscal year, July to June | interview | Q4 |
| D5 | Page `board-revenue` has a card, a line by month and a matrix by territory | plan | step 1 |
| D6 | Revenue shown in £M with one decimal | AGENTS.md | §Report standards |
| D7 | The line chart overlays the two years on a July to June axis | assumption | not agreed |
