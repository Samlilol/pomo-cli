# pomo-cli

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Local work observability runtime for agent-assisted work.

`pomo-cli` gives an agent a deterministic local interface for starting, resuming,
tracking, and completing task-linked work sessions without needing a GUI, daemon,
or cloud service.

## What

`pomo-cli` is a local-first CLI and optional MCP server for task and session
tracking in agent-assisted workflows. It is built for workflows where an agent
helps the user pick a real task, estimate a session, start tracking locally,
recover from interruptions, and close the loop with a trustworthy summary.

The product is not just "a timer in the terminal." It is a small local runtime
for task identity, session lifecycle, and worked-today visibility.

The canonical product definition lives in `PRD.md`.

## Why

Most timer tools are built for humans clicking buttons. `pomo-cli` is built for
agents that need stable task identity, explicit session lifecycle, and a
machine-friendly surface they can drive repeatedly without losing context.

It deliberately optimizes for:

- local-first state
- deterministic commands
- explicit task/session tracking
- task-level identity instead of app-level tracking
- easy handoff between CLI and MCP
- a small operational footprint

## Current Status

What works today:

- local SQLite-backed task and session tracking
- CLI commands for `start`, `plan`, `continue`, `watch`, `status`, `complete`, `summary`, and `backlog`
- optional MCP server exposing the same core operations
- daily summaries with worked-today totals, completed-today totals, and per-task time

What is not built yet:

- human vs agent vs review vs idle time classification
- durable end-of-task summary generation
- confirmed post-backs to Linear, Slack, or Git

## Who It's For

- people using Claude Code, Codex, or similar terminal-first agents
- users who want focused work sessions tracked locally
- workflows where task identity, resume behavior, and worked-today summaries matter

## What It's Not

- not a full project manager
- not a cloud sync product
- not a desktop notification app
- not a network service; `pomo-mcp` is local stdio only

## Install

From GitHub:

```bash
pip install "pomo-cli @ git+https://github.com/Samlilol/pomo-cli.git"
pip install "pomo-cli[mcp] @ git+https://github.com/Samlilol/pomo-cli.git"   # optional MCP server support
```

`pip install` only installs the runtime commands (`pomo` and, with the extra,
`pomo-mcp`). To make Codex or Claude auto-trigger `pomo` in other projects,
install the agent skill globally too.

From a cloned checkout:

```bash
mkdir -p ~/.codex/skills/pomo ~/.claude/skills/pomo
cp .claude/skills/pomo/SKILL.md ~/.codex/skills/pomo/SKILL.md
cp .claude/skills/pomo/SKILL.md ~/.claude/skills/pomo/SKILL.md
```

Without cloning the repo:

```bash
mkdir -p ~/.codex/skills/pomo ~/.claude/skills/pomo
curl -fsSL https://raw.githubusercontent.com/Samlilol/pomo-cli/main/.claude/skills/pomo/SKILL.md \
  -o ~/.codex/skills/pomo/SKILL.md
cp ~/.codex/skills/pomo/SKILL.md ~/.claude/skills/pomo/SKILL.md
```

After this, agent clients that load global skills can recognize work intent
such as "write me a 300-word essay", start `pomo`, do the work, and complete
the task.

For local development:

```bash
cd pomo-cli
python3 -m venv /tmp/pomo-cli-venv        # use a path without spaces
. /tmp/pomo-cli-venv/bin/activate
pip install -e .
python -m unittest -v
```

> If your checkout path contains spaces (e.g. `/Users/you/Desktop/Study Repo`), keep the venv at a path without spaces like `/tmp/pomo-cli-venv`. The generated `pomo` script needs a valid interpreter path.

Install the optional extra when you want MCP server support or want the MCP
integration tests to run locally instead of being skipped:

```bash
pip install -e ".[mcp]"
```

## Product Layers

### Core Runtime Loop

The core loop is the smallest useful workflow:

1. tell the agent what to focus on
2. let the agent start a local session
3. interrupt or resume if needed
4. explicitly mark the task done
5. inspect today's summary

```bash
pomo start --task "write 500-word essay" --minutes 25
pomo status
pomo complete --latest
pomo summary
```

Use `pomo watch` when you want to attach a visible countdown to the active
session. Use `--watch` when you want `start` or `continue` to block and show
the countdown immediately.

This is the primary product path. If you only use these commands, `pomo-cli`
still delivers its core value.

`pomo summary` reports:

- tasks worked today
- tasks completed today
- total time spent today
- per-task elapsed totals

### Planning Layer

Use the planning layer when the next task is not obvious and the agent should
help turn a messy todo list into an ordered backlog.

```bash
pomo plan --file today-plan.json
pomo backlog
pomo start --position 1
pomo start --task-id 2026-0410-0001
pomo start --task-id 2026-0410-0001 --minutes 30
```

`pomo run` remains available as a backwards-compatible alias for starting
planned backlog tasks, but new workflows should use `pomo start`.

### Agent / MCP Layer

Use the MCP layer when you want a trusted local interface that an agent client
can call directly.

```bash
pip install "pomo-cli[mcp]"
pomo-mcp
```

`pomo-mcp` is optional. The CLI remains the base product.

## Quick Start: Single-Task Agent Loop

This is the shortest path to the product's value.

1. User tells the agent what they want to focus on.
2. Agent estimates a session and starts tracking.

       pomo start --task "write 500-word essay" --minutes 25

3. Agent works on the task while the session remains active.

4. Agent checks the current state or attaches a visible countdown if useful.

       pomo status
       pomo watch

5. Agent starts another round if the task is not done yet.

       pomo continue --minutes 25

   Add `--watch` to block and display the countdown immediately:

       pomo continue --minutes 25 --watch

6. When the user finishes, the agent closes the task explicitly.

       pomo complete --latest

7. Agent shows what got done today.

       pomo summary

   This includes tasks worked today, tasks completed today, total time spent
   today, and per-task elapsed totals.

For a fresh data directory, set `HOME` to a temporary directory before running.

## Task Identity

`pomo-cli` owns task identity. Agents should reuse the returned `task_id` when
continuing or completing work.

Task IDs are generated by the CLI and follow the format `YYYY-MMDD-NNNN` (year, month, day, sequence number). Example on April 6 2026:

- first task: `2026-0406-0001`
- second task: `2026-0406-0002`

Always reuse the `task_id` returned by `start` when continuing or completing a task.

## Planning Flow

Create a JSON file with a parent title and planned subtasks:

```json
{
  "parent_title": "Today plan",
  "subtasks": [
    {"task_title": "Finish lecture 6", "estimate_minutes": 45, "priority": "high"},
    {"task_title": "Write notes", "estimate_minutes": 20, "priority": "medium"}
  ]
}
```

`priority` must be `high`, `medium`, or `low`.

Load it into today's backlog:

    pomo plan --file today-plan.json

View the ordered backlog:

    pomo backlog

Start a task by position or task ID:

    pomo start --position 1
    pomo start --task-id 2026-0410-0001

Use `start` for brand new ad hoc tasks and `continue` for tasks that already have session history.
`run` is still supported as a compatibility alias for planned backlog tasks.

## State Model

```
planned → running → session_closed → running  (via continue / start)
                 ↘               ↘
                  completed       completed
```

- **planned** — in backlog, not yet started
- **running** — session active; multiple tasks may have active sessions, but a single task may not have more than one active session
- **session_closed** — countdown hit 0 in `watch`; elapsed time recorded, task not yet done
- **completed** — explicitly marked done via `pomo complete`

## MCP Server

Install the optional extra to enable the local MCP server:

```bash
pip install "pomo-cli[mcp]"
```

Verified client configs:

```json
// Claude Code: ~/.claude/claude_code_config.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }

// Cursor: .cursor/mcp.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }

// Windsurf: ~/.codeium/windsurf/mcp_config.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }
```

Any stdio-compatible MCP client can also connect to `pomo-mcp`.

`pomo-mcp` is a local stdio server. It reads and writes the user's local `~/.pomo-cli/pomo.db`. Only connect it to trusted local agent clients. Do not expose it as a network service.

## Agent Sample Flows

These are more advanced examples. The product does not require Slack or Linear to
be useful. See `AGENTS.md` for the full agent usage guide.

### Flow 1: Agent Finds Today's Todos, Breaks Them Down, Then Runs

1. User asks the agent to find today's todos from Slack MCP and Linear MCP.
2. Agent normalizes them into a short "today plan".
3. Agent writes a local `today-plan.json` and runs:

       pomo plan --file today-plan.json

4. Agent shows the resulting backlog:

       pomo backlog

5. User picks a task (for example, backlog position 1). Agent runs:

       pomo start --position 1

Best when the source todo list is messy, spread across tools, or needs decomposition.

### Flow 2: Agent Finds Highest-Priority Todo and Starts Immediately

1. User asks the agent to find today's highest-priority todo.
2. Agent resolves it directly from Slack MCP / Linear MCP.
3. If the task is already in the backlog:

       pomo start --task-id <id>

4. If not yet in the backlog, agent creates a one-item plan first:

       pomo plan --file today-plan.json
       pomo start --position 1

5. User can later use `pomo watch`, `pomo status`, `pomo complete --latest`.

Best when the agent can confidently pick the next task without a planning round.

## For Contributors and Agents

- **`CLAUDE.md`** — project context for Claude Code: dev setup, architecture, how to add commands.
- **`AGENTS.md`** — agent usage guide: full command reference, state model, workflow patterns, estimation heuristics.
- **`.claude/skills/pomo/SKILL.md`** — agent skill that auto-loads when this repo is open. Copy it to `~/.codex/skills/pomo/SKILL.md` and/or `~/.claude/skills/pomo/SKILL.md` for global availability.
