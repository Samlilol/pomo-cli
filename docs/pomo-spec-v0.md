# Pomo CLI Spec v0

## What

`pomo-cli` is a local terminal pomodoro tool designed for an agent-assisted workflow.

Primary interaction:

1. User tells an agent what they want to focus on.
2. The agent estimates how long one session should be.
3. The agent starts a pomo session in the terminal.
4. If the user finishes early, the agent marks the task as complete.
5. The CLI tracks elapsed time and provides a lightweight daily summary.

Example:

- User: `我現在要 focus 寫 500 字 essay，幫我開 pomo 計時`
- Agent reasoning: `500-word essay ~= 30 minutes`
- Agent reply: `現在幫你打開 pomo 計時，完成時間預約 30 分鐘`
- User confirms
- Agent runs: `pomo start --task "write 500-word essay" --minutes 30`
- Terminal shows countdown: `30:00 -> 29:59 -> ...`
- User later says: `我寫完了`
- Agent runs: `pomo complete --task-id <id>`

## Why

The goal is not just "a timer". The goal is a timer that works cleanly with Codex / Claude Code style agents without overbuilding the first version.

This v0 intentionally optimizes for:

- fast local MVP
- clean terminal experience
- stable task tracking
- easy upgrade path to agent tooling later

It explicitly does not optimize for:

- background daemons
- desktop notifications
- multi-session queues
- cross-platform packaging
- full analytics dashboard
- Phase 1 MCP integration

## How

### Product scope

- Local CLI only.
- Single active session at a time.
- Foreground countdown in terminal.
- No notification support in v0.
- Summary only covers today.
- Summary only includes completed tasks.
- Daily summary is bucketed by `completed_at` in local system time.

### Agent / CLI responsibility split

- Agent is responsible for:
  - understanding natural language
  - estimating session length
  - deciding whether to start another round
- CLI is responsible for:
  - task identity
  - session lifecycle
  - elapsed-time accounting
  - today summary

### Commands

- `pomo start --task "<title>" --minutes <n>`
  - Starts a new task and its current session.
  - If the user later wants another round for the same task, the agent can call the same command with `--task-id`.

- `pomo start --task-id <id> --minutes <n>`
  - Starts another session for an existing task.
  - This replaces a separate `continue` command in v0.

- `pomo start --latest --minutes <n>`
  - Starts another session for the most recently tracked task.
  - This is an escape hatch for agent flows that no longer hold the explicit `task_id`.

- `pomo complete --task-id <id>`
  - Marks a task complete.
  - Records actual elapsed time only if the task is still actively running.
  - Used when the user says they finished early.

- `pomo complete --latest`
  - Marks the most recently tracked task complete.
  - This is an escape hatch when the agent loses the explicit `task_id`.

- `pomo status`
  - Returns the current tracked task state.

- `pomo summary`
  - Returns today's completed-task summary.

### Core data model

- `task_id`
  - Stable identifier owned by the CLI.
  - Used for aggregation and continuation.

- `task_title`
  - Human-readable display name.

- `planned_minutes`
  - Duration planned for the current session.

- `starts_at`
  - Session start timestamp.

- `ends_at`
  - Planned end timestamp.

- `remaining`
  - Remaining time for the active session.

- `total_time_spent`
  - Actual elapsed time accumulated for the task across sessions.

- `state`
  - Task/session lifecycle state.
  - Allowed values in v0: `running`, `session_closed`, `completed`.

- `completed_at`
  - Timestamp when the task is explicitly marked complete.
  - Used to bucket tasks into `summary(today)`.

### State model

- `running`
  - A session is actively counting down in the terminal.

- `session_closed`
  - The current session has ended and its elapsed time has been recorded, but the task is not yet explicitly done.
  - This is the state after a timer reaches `0` without a `complete`, or if the foreground session exits before explicit completion.

- `completed`
  - The task has been explicitly marked done by the user or agent.

Valid transitions:

- `running -> session_closed`
- `running -> completed`
- `session_closed -> running`
- `session_closed -> completed`

### Command semantics

`start`
- Creates a task on first use.
- Reuses an existing task when called with `--task-id`.
- Supports `--latest` as a fallback when the agent no longer has the explicit task identifier.
- Immediately enters terminal countdown mode.
- If the countdown reaches `0` without an explicit completion, the session closes, elapsed time is recorded, and the task moves to `session_closed`.
- If the foreground session exits before explicit completion, elapsed time is recorded and the task moves to `session_closed`.

`complete`
- Ends the task as completed.
- Records actual elapsed time, not planned time, for any still-running session.
- Does not double-count elapsed time if the task is already in `session_closed`.
- Example: a 30-minute session completed after 12 minutes adds 12 minutes.
- Can be called while the task is `running` or after it is already `session_closed`.
- Supports `--latest` as a fallback when the agent no longer has the explicit task identifier.

`status`
- Focused on "what is happening now", not analytics.
- Returns the tracked task state, which may be `running`, `session_closed`, or `completed`.
- Suggested output fields:
  - `state`
  - `task_id`
  - `task_title`
  - `planned_minutes`
  - `remaining`
  - `starts_at`
  - `ends_at`
  - `total_time_spent`

`summary`
- Focused on "what got done today".
- Includes only tasks in `completed` state.
- Buckets tasks by `completed_at`, using the local system date.
- Suggested output fields:
  - `tasks_completed`
  - `total_time_spent_today`
  - `time_spent_by_task`

## Key trade-offs and justification

### Why CLI-first instead of MCP-first

We discussed `CLI + MCP`, but v0 chooses CLI first because:

- it validates the user experience faster
- it keeps the first build small
- it avoids protocol work before the core timer behavior is proven
- it still leaves a clean path to MCP later

### Why no separate `continue` command

We originally considered:

- `start(task_title, duration_minutes)`
- `continue(task_id, duration_minutes)`

That is clear, but for CLI v0 it is more surface area than needed. A single `start` command with either `--task` or `--task-id` keeps the intent clear while reducing command count.

### Why no separate `watch` command

We considered splitting timer display into:

- control commands
- terminal renderer

That is a good fit for a future MCP architecture, but it is unnecessary for v0. For the first version, `start` can directly own the foreground countdown experience.

### Why keep `status` and `summary` separate

These answer different questions:

- `status`: what is happening right now
- `summary`: what was completed today, based on completion time

Combining them would make parsing harder for agents and make the CLI less predictable.

### Why task identity belongs to the CLI

If the agent invents task names repeatedly, the names may drift:

- `write 500-word essay`
- `write 500-word essay-2`

That would break aggregation. The CLI therefore owns `task_id`, and the agent should reuse that `task_id` when starting another session for the same task.

### Why `total_time_spent` uses actual elapsed time

Planned time and actual time answer different questions.

- planned time tells the timer how long to run
- actual elapsed time tells the summary how much focus time was truly spent

For v0, `total_time_spent` should always use actual elapsed time.

### Why `session_closed` and `completed` are separate

A closed session and a completed task are not always the same thing.

- `session_closed` means the timer session ended and was recorded
- `completed` means the user explicitly said the task is done

This keeps the timer honest without forcing every ended session to mean "the work is finished."

### Why completed-only summary

The first summary is intended to feel like a lightweight "done today" report, not a full dashboard. Excluding in-progress work keeps the output simple and unambiguous.

### Why add `--latest`

The intended caller is an agent, and agent context can drift.

`--latest` is a small escape hatch that keeps the CLI ergonomic when the agent no longer holds the exact `task_id`, without requiring fuzzy task matching.

## Out of scope for v0

- MCP server
- HTTP API
- desktop notifications
- pause / resume
- cancel semantics
- partial-session analytics beyond elapsed time
- visual dashboard
- historical summary beyond today

## Phase 2 direction

The most likely Phase 2 is MCP, not a general-purpose API.

Reason:

- the intended caller is an agent
- the tool is local and interactive
- the command surface is already tool-shaped

The natural Phase 2 path is:

1. keep the CLI core as the source of truth
2. wrap `start`, `complete`, `status`, and `summary` as MCP tools
3. optionally re-split countdown rendering from control if needed

## MCP vs API

### MCP

Use MCP when the primary consumer is an agent that wants structured tools.

Pros:

- natural fit for Codex / Claude Code tool calling
- structured inputs and outputs
- less shell parsing
- good for local capabilities

Cons:

- mainly useful in agent ecosystems
- not a general integration surface for normal apps

### API

Use an API when the primary consumer is another app, frontend, or remote service.

Pros:

- universal integration surface
- works for web, mobile, backend, automation, and agents
- good if the timer becomes a standalone service

Cons:

- more infrastructure and lifecycle overhead
- unnecessary for a local terminal MVP

### Recommendation

For this project:

- v0: CLI only
- Phase 2: MCP
- API: only if the project later needs non-agent clients or remote access
