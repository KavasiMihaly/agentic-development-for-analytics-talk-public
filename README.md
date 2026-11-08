# Agentic Development for Analytics

The slides and a starter kit from my session at **Data & AI Builders Conference 2026**, Bergamo, 7 November 2026.

> The agent is good enough. The question now is whether you would be happy to take responsibility for what it delivered.

**[Watch the deck](https://selfservicebi.co.uk/agentic-development-for-analytics-talk-public/)** · [Session page](https://sessionize.com/s/mihalykavasi/agentic-development-for-analytics-build-your-ai-to/155049)

The deck is as delivered on the day, so it still points to other sessions from that conference. The demos are silent recordings: click a showcase slide to play its clip. Use the arrow keys, or `Esc` for the overview.

The Halden company in the deck and in the example is fictional.

## The kit

The talk treats skills, agents, hooks and MCP as control levers: each one decides how much the agent can do on its own, and how sure you can be of the result. This kit is the part you can reuse.

| Part | What it gives you | How it gets there |
|---|---|---|
| `requirements-interview` skill | At most five questions, then a plan it waits for you to approve, then a decision log | Plugin |
| `plan-reviewer` agent | A read-only reviewer: is each measure and page in the plan, logged and sourced? | Plugin |
| Data boundary hook | The agent can't read data files or run ad-hoc queries. It checks numbers with tools that return a verdict | Plugin |
| Action trace hook, `show-trace` skill | One line per tool call, with no file contents, so you can see what happened | Plugin |
| `AGENTS.md` template | Your definitions, standards and never-list, in the structure used in the talk | Copy |
| Permission rules | Ask before git and installs; deny edits to the checks | Copy |
| [Power BI gate](kit/powerbi-gate/README.md) (optional) | Relationship, best-practice, report and decision-trace checks, locally and on pull requests | Copy |

### Add it to a project

You need Claude Code and Python 3.9 or later, available as `python`. No other packages are needed for the plugin.

**1. Install the plugin, in your project folder:**

```bash
claude plugin marketplace add KavasiMihaly/agentic-development-for-analytics-talk-public
```

```bash
claude plugin install agentic-analytics-kit@agentic-analytics --scope project
```

Use `--scope project`. At user scope, the data boundary applies to every project on your machine.

**2. Copy two files** from [`kit/copy-into-your-project/`](kit/copy-into-your-project/), because a plugin can't install them:

| From | To |
|---|---|
| `AGENTS.template.md` | `AGENTS.md` in your project root. Fill in the placeholders, starting with Definitions |
| `settings.example.json` | `.claude/settings.json`. Merge it if you already have one, and remove rules for folders you don't use |

Optional: `mcp.example.json` becomes `.mcp.json` for Microsoft's Power BI modeling MCP server (the example is for Windows), and `data-boundary.example.json` becomes `.claude/data-boundary.json` to add your own check tools or file types.

See a filled-in version in [`kit/examples/halden/`](kit/examples/halden/).

**3. Restart Claude Code and ask for a report.** To confirm the boundary is on, ask it to read a CSV file: it should be denied.

### Worth knowing

- **Hooks are a seatbelt, not a vault.** They read what a command says, and a determined agent might get round them. For real customer data, the real boundary is what the agent's identity is allowed to read.
- **If Python is missing, the data boundary blocks tool calls** rather than letting them through.
- **`AGENTS.md` also works with other agents.** The plugin and hooks are specific to Claude Code.
- The run traces go in `.trace/`, which ignores itself in git.

Run the kit's tests with `python -m unittest discover -s kit/tests`.

### What's not here

The model and report templates, the deploy script and the data contract are tied to the fictional company and its Fabric setup, so they stayed out. For an install guard and fuller session logs, see [Claude Code Essentials](https://github.com/KavasiMihaly/Claude-Code-Essentials).

## Licence

The kit is [MIT](LICENSE). The deck's content is not: see [NOTICE](NOTICE.md).

## Author

**Mihaly Kavasi**, [One Day Business Intelligence](https://www.onedaybi.com) · [Self-Service BI blog](https://selfservicebi.co.uk) · [LinkedIn](https://www.linkedin.com/in/kavasimihaly/)
