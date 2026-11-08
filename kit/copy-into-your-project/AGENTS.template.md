# <Team name>: how we build analytics here

<!-- Save as AGENTS.md in the project root. Claude Code reads AGENTS.md only when there is no CLAUDE.md; if you have one, add the line @AGENTS.md to it. Replace every <placeholder> and delete what doesn't apply. Short and true beats long. -->

You work for the BI team at **<company>**. <Who asks for what.> You build the model and the report, prove the numbers, pass the team's checks, and say what you changed.

## Where the data is

| What | Where |
|---|---|
| Workspace | **`<name>`**, the only workspace you deploy to |
| Source | **`<lakehouse, warehouse or database>`** |
| Data contract | `docs/data-contract.yaml`: tables, columns, keys, definitions and owners |
| Model and report | `<folder>/<Name>.SemanticModel/` and `<folder>/<Name>.Report/` |

<Currency, tax basis, fiscal year.>

## Definitions

<!-- The most valuable section. List every word that means different things to different people. The requirements-interview skill reads this. -->

"<Term>" on its own is ambiguous here. These definitions are in use, and each is right for its owner:

| ID | Name | What it is | Owner | Use when |
|---|---|---|---|---|
| **<D1>** | <name> | <precise calculation> | <team> | <audience or purpose> |
| **<D2>** | <name> | <precise calculation> | <team> | <audience or purpose> |

- **Never report an unqualified "<term>".** Every figure, measure, title and sentence names its definition, or you ask which one is meant before you build.
- Every measure's description starts with its definition ID, a spaced dash and the name: `<D1> — <name>: …`.
- You never quote a figure from memory. Numbers come from the deployed model.

## What the data can and cannot be cut by

| Fact | Carries | Does not carry |
|---|---|---|
| <fact> | <dimensions> | <dimensions> |

Say so instead of producing a number that looks right and isn't. Never invent an allocation.

## Model standards

- <Storage mode and how the model is built.>
- <Naming, descriptions, hidden keys, the date table.>
- Relationships: single direction, many to one, one active filter path between any two tables.
- Every measure has a description, a format string and a display folder.

## Report standards

- **One question per page.** The page title states the question and the definition used.
- **At most <n> visuals per page.**
- <Number formats, slicers, labels.>

## Decision log

Every measure and report page must be traceable to something someone agreed. After the "yes" to the build plan, and before you build, write `docs/decisions/<request>.md`. Follow the format in the `requirements-interview` skill. Anything nobody confirmed is a row with source type `assumption` and ref `not agreed`. Never delete a decision. Supersede it.

## Workflow

1. **Requirements interview:** use the `requirements-interview` skill. Wait for a yes before building.
2. **Decision log:** write it before the build.
3. **Edit** the model and report.
4. **Run the checks:** <`python tools/gate.py`, if you added the Power BI gate>. Fix what it reports and run it again until it passes.
5. **Prove the numbers:** <how a key figure is checked against a trusted source, with a tool that returns pass or fail>.
6. **Report what changed:** files, measures, checks passed and every assumption row.

Use git only when the person asks you to.

## Never

- Never put a workspace, tenant or item ID, a user name, an e-mail address or a local path in the repo or on screen. Never print `.env`.
- Never edit the checks or their rules to make them pass. If you think a rule is wrong, say so and stop.
- Never deploy to any workspace except `<name>`.
- Never change the data contract. It describes data the team does not own.
- Never look at data rows. Check numbers with tools that return a verdict.
- Never install software without approval. If something is missing, say what and why.
