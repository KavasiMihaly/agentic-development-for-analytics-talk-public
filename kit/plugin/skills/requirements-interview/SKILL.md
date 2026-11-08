---
name: requirements-interview
description: Use before building or changing a report, page, semantic model or measure when the request uses a business term that AGENTS.md lists as ambiguous, or does not say who it is for, which definition applies or which period it covers. Asks at most five questions in one message, then proposes a build plan and waits for confirmation.
---

# Requirements interview

Business terms have more than one right answer. Find out which one is wanted, quickly, then build.

Read the project's `AGENTS.md` first. Its **Definitions** section lists the terms that are ambiguous, what each option means and who owns it. If it has none, tell the person, then ask anyway.

## The checklist

Ask only what the request has not already answered. Number each question with its number in this checklist, put them in **one message**, and give each a recommended answer so the person can reply "go with your suggestions".

| # | Ask | Why |
|---|---|---|
| 1 | **Who is it for, and what decision does it support?** | The audience picks the definition and the level of detail |
| 2 | **Which definition of the main measure?** | One word can hide several numbers. Offer the options from `AGENTS.md` |
| 3 | **Which meaning of any other ambiguous term?** Only if the request uses one | For example, a dimension that exists in two versions |
| 4 | **Which calendar?** | Fiscal and calendar years give different answers |
| 5 | **Which period, and compared with what?** | Sets slicers, comparisons and the time measures |

Suggest the answer to question 2 from the answer to question 1, using who owns each definition.

Do not ask what the project already settles in `AGENTS.md` or its data contract.

## The stop rule

- **Five questions at most**, in one round. Three is better when the request already answers some.
- If an answer leaves something open, choose the default, say it is an assumption, and carry on. Do not start a second round.
- If the person says "you decide", use the defaults and list them in the plan.

## Check the request against the grain

Before you propose, check each cut against what the data can support. If something cannot be built as asked, say so in the plan and offer what can be. Never invent an allocation to make a number appear.

## Turn the answers into a build plan

Reply with a short plan in this shape, then **wait for a yes** before you build.

```
Plan: <report name> for <audience>
Definition: <ID and name of the definition used>
Time: <calendar, period, comparison>

Page 1 — <question>? (<definition>)
  <visual>: <measure> by <dimension>
  slicers: <fields>
Page 2 — <question>? (<definition>)
  ...

Model: existing measures; new: <measure> (<definition>)
Checks: <the checks that will run>
Assumptions: <anything you chose by default>
Not possible as asked: <cut> — offered <alternative>
```

- One question per page.
- Every page title states the question and the definition.
- Reuse existing measures. Add one only for something they do not cover.

## After the yes: record it

Before you build, write `docs/decisions/<request>.md`, following [decision-log.md](decision-log.md):

1. **Interview**: every checklist item as Q1–Q5 with its answer. An item the request answered gets "In the request: …"; a default you chose is marked "(default, in the agreed plan)".
2. **Plan**: the plan as it was agreed, as numbered steps.
3. **Decisions**: a row for every measure and every page, and for every other choice behind them. Cite the interview answer, the contract entry, the `AGENTS.md` section or the plan step it comes from. A choice none of them made is an `assumption`, `not agreed`.

Never cite a source that does not say what the row says. List the assumptions when you report back.
