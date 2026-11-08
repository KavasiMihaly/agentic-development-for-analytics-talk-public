# Halden BI team: an extract

Halden Industrial Supplies is a fictional company built for the talk. This extract shows the [template](../../copy-into-your-project/AGENTS.template.md) filled in, using only what the session showed.

## Definitions

"Revenue" on its own is ambiguous at Halden. Two of the definitions in use:

| ID | Name | What it is | Owner | Use when |
|---|---|---|---|---|
| **R2** | Net revenue | Invoiced revenue minus credit notes | Finance | Finance's monthly figures |
| **R3** | Board revenue | Net of credits and accrued rebates. Reconciles to the ledger | The board pack | Board reporting; anything that must agree with the ledger |

- **Never report unqualified revenue.** Every figure, measure, title, label and sentence that says "revenue" or "sales" names its definition, or you ask which one is meant before you build.
- Never create a measure called plain `Revenue`, `Sales` or `Total Revenue`; the gate blocks it.

## Report standards

- **One question per page.** The page title states the question and the definition used.
- Revenue in £M with one decimal.
- Every territory visual says which territory: sales or geographic.

## Never

- Never look at data rows. Check numbers with the tools that return a verdict. A hook enforces this; if it denies a step, use those tools and do not look for a way round it.
