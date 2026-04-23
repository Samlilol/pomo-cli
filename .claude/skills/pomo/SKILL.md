---
name: pomo
description: Use when the user wants to start or resume a focus session, track work time, plan tasks, check what they worked on today, or manage their pomo-cli backlog. Triggers on phrases like "open pomo", "start a timer", "pomo 計時", "幫我開 pomo", "help me focus", "start a focus session", "mark it done", "complete the task", "what did I work on today", "pomo summary", "pomo status", or anything involving pomo-cli task management. ALSO triggers when the user's message expresses intent to work on something — ticket IDs (LIN-\d+, #\d+, PROJ-\d+), natural language ("help me review X", "let's work on Y", "build/fix/debug X"), or tasks surfaced from Slack/Linear MCP.
metadata:
  version: 2.0.0
---

# Pomo CLI Skill

You are helping the user manage focus sessions using `pomo-cli`, a local focus runtime for agent-assisted work.

`pomo-cli` is not just a timer in the terminal. It is a deterministic local interface
for starting, resuming, tracking, and completing real work sessions, with optional
planning and MCP layers on top.

## Setup Check

First, verify the CLI is available:

```bash
which pomo
```

If not found, fall back to running from the project directory:

```bash
cd <repo-root> && python3 -m pomo_cli <subcommand>
```

Or activate the venv if needed:

```bash
. /tmp/pomo-cli-venv/bin/activate && pomo <subcommand>
```

Optional MCP support:

```bash
pip install "pomo-cli[mcp]"
```

---

## Command Reference

### Core focus loop

### Start a brand new ad hoc task
```bash
pomo start --task "<title>" --minutes <n>
```
- This creates a new task, opens a live countdown in the terminal.
- **Save the `task_id` from the output** — you'll need it to continue or complete.

### Plan a structured day from a JSON file
```bash
pomo plan --file today-plan.json
```
Plan file format:
```json
{
  "parent_title": "Today plan",
  "subtasks": [
    {"task_title": "Finish lecture 6", "estimate_minutes": 45, "priority": "high"},
    {"task_title": "Write notes", "estimate_minutes": 20, "priority": "medium"}
  ]
}
```
Priority must be: `high`, `medium`, or `low`.

### Start a planned backlog task
```bash
pomo run --position 1              # by backlog position
pomo run --task-id <id>            # by explicit task id
pomo run --task-id <id> --minutes 30  # override the estimate
```

### View today's backlog
```bash
pomo backlog
```

### Continue a task (add a new session to an existing task)
```bash
pomo continue --minutes <n>            # continues latest worked task
pomo continue --task-id <id> --minutes <n>
```

### Re-attach to the live countdown
```bash
pomo watch
```

### Check current task state
```bash
pomo status
```
Returns: state, task_id, task_title, planned_minutes, starts_at, ends_at, total_time_spent.

### Mark a task complete
```bash
pomo complete --task-id <id>   # preferred — use the id from start output
pomo complete --latest          # fallback if you've lost the id
```

### Today's summary
```bash
pomo summary
```
Shows tasks worked today, tasks completed today, total time spent today, and per-task breakdown.

### Planning layer

### Flow A — Single-task loop (most common)
1. User describes what they want to focus on.
2. Estimate the session length from the task scope (e.g. "write 500 words" → 25–30 min).
3. Confirm with the user if unclear.
4. Run: `pomo start --task "<title>" --minutes <n>`
5. **Record the `task_id`** from the status output.
6. When user says they're done: `pomo complete --task-id <id>`
7. If you've lost the id: `pomo complete --latest`

### Flow B — Structured planning
1. Collect tasks (from user, Slack MCP, Linear MCP, etc.).
2. Break into subtasks with `estimate_minutes` and `priority`.
3. Write a `today-plan.json` file.
4. Run: `pomo plan --file today-plan.json`
5. Show the backlog: `pomo backlog`
6. When user picks a task: `pomo run --position <n>`

### Agent / MCP layer

Optional MCP support:

```bash
pip install "pomo-cli[mcp]"
```

Use MCP when the agent client should call a trusted local interface directly instead
of shelling out through CLI commands.

---

## State Model

```
planned → running → session_closed → running (continue)
                 ↘                ↘
                  completed        completed
```

- **planned** — in the backlog, not yet started
- **running** — countdown active in terminal
- **session_closed** — timer hit 0 or Ctrl+C, elapsed time recorded, task not yet done
- **completed** — explicitly marked done

Key rules:
- Multiple active sessions across different tasks are allowed.
- A single task cannot have more than one active session at a time.
- `run` / `continue` fail if that same task is already running. `start` creates a new task session.
- `complete` works whether the task is `running` or `session_closed`.

---

## Agent Workflow

### Flow C — Continue an interrupted session
1. Check status: `pomo status`
2. If state is `session_closed`, ask how long the next session should be.
3. Run: `pomo continue --minutes <n>` (or with `--task-id`)

---

## Estimation Heuristics

When the user doesn't specify minutes, estimate from the task:

| Task type | Suggested session |
|---|---|
| Read one chapter / watch one lecture | 30–45 min |
| Write 300–500 words | 25–30 min |
| Write 1000+ words | 45–60 min |
| Code one small feature | 25–45 min |
| Review / edit a document | 20–30 min |
| Quick research or note-taking | 20–25 min |

When uncertain, ask: "How long do you want to set the timer for?"

---

## Tips

- Always report the `task_id` to the user after `start` or `run` so they can reference it later.
- Use `pomo status` to check state before deciding which command to run next.
- Use `--latest` only as a fallback — prefer explicit `--task-id` to avoid ambiguity.
- `pomo summary` is useful for end-of-day review: "here's what you got done today."
- The countdown runs in the foreground. After starting, tell the user the timer is running and they can Ctrl+C and re-attach later with `pomo watch`.

---

## Auto-Trigger Rules

Auto-trigger fires when you detect a clear work intent in the user's message. Do this silently — do not interrupt the conversation.

**Signal A — Structured ticket ID**
Message contains `LIN-\d+`, `#\d+`, `PROJ-\d+`, etc.
→ Use the ticket ID string as task title (e.g. "LIN-247")

**Signal B — Natural language task intent**
Phrases like "help me [verb] [noun]", "review X", "build/fix/debug X", "let's work on X", or tasks surfaced from standup or meetings.
→ Extract a concise task title (≤60 chars), e.g. "review UIUX", "develop feature X"

**Signal C — External tool source**
Tasks pulled via Slack MCP (standup notes) or Linear MCP (ticket assigned):
→ Use the ticket title or Slack message summary as task title

**Action for all three:**
1. Extract concise task title.
2. Run `pomo status` — if that exact title is already running, continue silently.
3. If not running: `pomo start --task "<title>" --minutes 25`
4. Confirm briefly: "Session started: '<title>'." — do not interrupt conversation flow.

Multiple sessions can run in parallel. You may start a session for a new task even if another is already running.

---

## Completion Detection

When you detect completion signals (user says "done", "that works", "fixed it", "ship it", or a git commit references the task):
1. Run `pomo status` to get elapsed time.
2. Say: "{elapsed} min on '<task>'. Mark it complete?"
3. If user confirms: `pomo complete --task-id <id>` (preferred) or `pomo complete --latest`
4. Offer Linear post-back if the task title is a Linear ticket ID (see below).

---

## Linear Post-Back (after pomo complete)

After completing a task whose title matches a Linear ticket ID (`LIN-\d+`):
1. Ask: "Want me to update Linear ticket {id}?"
2. If user confirms:
   - Linear MCP `update_issue`: set status to Done
   - Linear MCP `create_comment`: "Completed in {elapsed_min} min via pomo-cli on {date}."
3. Confirm when done.

---

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
