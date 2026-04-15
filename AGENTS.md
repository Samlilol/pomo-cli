# pomo-cli — Agent Guide

This file is for AI agents (Claude Code, Codex, etc.) that want to drive `pomo-cli` on behalf of a user.

`pomo-cli` is a local focus runtime for agent-assisted work. The CLI is the base
product; planning and MCP are optional layers on top of the same local task/session
state.

## Invoking the CLI

If `pomo` is on PATH (installed via `pip install -e .` or `pip install pomo-cli`):

```bash
pomo <subcommand>
```

Otherwise, from the repo root:

```bash
python3 -m pomo_cli <subcommand>
```

For MCP support, install the optional extra:

```bash
pip install "pomo-cli[mcp]"
```

## Command Layers

### Core focus loop

```bash
# Start a new ad hoc task
pomo start --task "<title>" --minutes <n>

# Load a structured plan into today's backlog
pomo plan --file today-plan.json

# Start a planned backlog task
pomo run --position <n>
pomo run --task-id <id>
pomo run --task-id <id> --minutes <n>   # override estimate

# View today's backlog
pomo backlog

# Add a new session to an existing worked task
pomo continue --minutes <n>
pomo continue --task-id <id> --minutes <n>

# Re-attach to the live countdown
pomo watch

# Check current task state
pomo status

# Mark a task complete
pomo complete --task-id <id>
pomo complete --latest              # fallback if task_id is lost

# Today's time summary
pomo summary
```

### Planning layer

Use the planning layer when the agent should turn a messy todo list into a local
backlog before starting work.

### Agent / MCP layer

Use the MCP layer when the agent client should call `pomo-mcp` directly instead of
shelling out through CLI commands.

## Plan File Format

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

## State Model

```
planned → running → session_closed → running  (via continue/run)
                 ↘               ↘
                  completed       completed
```

- `planned` — in backlog, not yet started
- `running` — countdown active, one active session allowed at a time
- `session_closed` — timer ended or Ctrl+C, elapsed time recorded, task not done yet
- `completed` — explicitly marked done via `pomo complete`

## Agent Rules

1. **Save `task_id` from the output of `start` or `run`.** You will need it for `continue` and `complete`. Prefer explicit `--task-id` over `--latest`.
2. **Check for an active session before starting one.** Run `pomo status` if unsure. Starting a second session while one is running will error.
3. **Use `complete`, not just letting the timer expire.** A session expiring moves the task to `session_closed`, not `completed`. Always call `pomo complete` when the user says they are done.
4. **`pomo summary` only shows completed tasks.** Use `pomo status` for in-progress state.
5. **The countdown is foreground.** After starting, inform the user the timer is running. They can Ctrl+C and re-attach with `pomo watch`.

## MCP Server

Verified MCP client configs:

```json
// Claude Code: ~/.claude/claude_code_config.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }

// Cursor: .cursor/mcp.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }

// Windsurf: ~/.codeium/windsurf/mcp_config.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }
```

`pomo-mcp` is a local stdio server. It reads and writes `~/.pomo-cli/pomo.db`. Only connect it to trusted local agent clients. Do not expose it as a network service.

## Typical Flows

### Ad hoc task
```
user says: "help me focus on writing my essay for 30 minutes"

pomo start --task "write essay" --minutes 30
# → save task_id from output

user says: "I'm done"

pomo complete --task-id <saved-id>
```

### Structured day planning
```
# write today-plan.json based on user's todo list
pomo plan --file today-plan.json
pomo backlog
# → show user the list, ask which to start

pomo run --position 1
```

### Resume after a break
```
pomo status
# → state: session_closed

pomo continue --minutes 25
```

### End-of-day review
```
pomo summary
```

## Session Length Heuristics

| Task | Suggested session |
|---|---|
| Read one chapter / watch one lecture | 30–45 min |
| Write 300–500 words | 25–30 min |
| Write 1000+ words | 45–60 min |
| Code one small feature | 25–45 min |
| Review / edit a document | 20–30 min |
| Quick research or note-taking | 20–25 min |

When uncertain, ask the user: "How long do you want to set the timer for?"
