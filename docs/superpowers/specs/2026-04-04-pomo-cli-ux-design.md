# Pomo CLI UX Refresh

## Goal

Make the CLI fit the real workflow better:

- `remaining` should not be a default status field when the user only wants the raw session times.
- Task IDs should be chronological and easy to scan.
- Re-running the latest task should use a dedicated `continue` command instead of overloading `start --latest`.
- `start` should still begin with a visible countdown, but leaving the countdown UI should not terminate the session.

## Current Problems

1. `status` mixes static task metadata with live countdown state. This makes the default output noisy for users who mainly care about `start`, `scheduled_end_at`, and accumulated time.
2. New task IDs are derived from the title slug, which is harder to scan and creates random suffixes on collisions.
3. Re-running a task requires `start --latest --minutes <n>`, which is technically workable but reads like a selector hack instead of a workflow action.
4. `start` enters a blocking countdown, and `Ctrl+C` currently closes the active session. That makes "stop watching the timer" behave like "stop the pomodoro."

## Recommended Approach

Keep countdown-first behavior on `start`, but split "watching" from "running" at the control level.

- `start` continues to create the session and immediately enter countdown mode by default.
- `Ctrl+C` during countdown exits the watch UI only; it does not close the session.
- Add a standalone `watch` command for re-attaching to the active session later.
- Add a dedicated `continue` command to resume the latest or a specific prior task.
- Generate new task IDs as `yyyy-ddmm-0001`, `yyyy-ddmm-0002`, and so on for the local day.

This preserves the existing muscle memory of "start and see the clock," while fixing the workflow bug that the same interruption key currently doubles as "end the session."

## Command Design

### `start`

Supported forms:

- `pomo start --task "write draft" --minutes 25`

Behavior:

- Requires `--task` and `--minutes`.
- Creates a brand new task and active session.
- Prints the task summary first.
- Immediately enters countdown mode.
- If the countdown reaches zero, the session is auto-closed and prints `00:00`.
- If the user presses `Ctrl+C`, countdown mode exits and the command returns `130`, but the session remains active and `running`.

### `watch`

Supported forms:

- `pomo watch`

Behavior:

- Attaches to the current active session.
- Only renders the live countdown.
- If no active session exists, it returns an error.
- If the timer reaches zero, it auto-closes the session and prints `00:00`.
- If the user presses `Ctrl+C`, the watch UI exits without mutating task or session state.

### `continue`

Supported forms:

- `pomo continue --minutes 25`
- `pomo continue --task-id 2026-0404-0001 --minutes 25`

Behavior:

- Starts a new session for an existing task.
- Defaults to the latest task when `--task-id` is omitted.
- Reuses the same countdown behavior as `start`.
- Rejects completed tasks, matching the current service rule.

### `complete`

No functional change.

- If the task has the active session, it finalizes that session and marks the task completed.
- If the task is not actively running, it only marks the task completed.

### `status`

Keep it as a static inspection command instead of a live-timer surface.

Default fields:

- `state`
- `task_id`
- `task_title`
- `planned_minutes`
- `starts_at`
- `scheduled_end_at`
- `total_time_spent`
- `completed_at` when present

Removed from default status output:

- `remaining`

`remaining` now belongs to `watch`, which is the command explicitly intended for live countdown inspection.

## Data Model Changes

No schema migration is required.

### Task ID generation

New tasks use the format:

- `YYYY-DDMM-NNNN`

Example on 4 April 2026:

- first task: `2026-0404-0001`
- second task: `2026-0404-0002`

Generation rule:

- Count the number of existing tasks whose `created_at` falls on the same local calendar day as `now`.
- Use that count plus one as the zero-padded sequence number.

Existing slug-based IDs remain valid and addressable. The new format applies only to newly created tasks.

## Runtime Behavior

### Countdown loop

Unify countdown behavior for both `start` and `continue`.

- Countdown uses the active session state, not a local in-memory timer.
- Hitting `Ctrl+C` exits the UI loop only.
- Auto-expiry closes the session through the service layer.
- External completion while watching prints a completion message and exits cleanly.

### Exit semantics

- `start` / `continue` on natural expiry: return `0`
- `watch` on natural expiry: return `0`
- `start` / `continue` on `Ctrl+C`: return `130`, session still `running`
- `watch` on `Ctrl+C`: return `130`, session still `running`

## Implementation Outline

1. Extend the parser with `watch` and `continue`.
2. Remove `--latest` from `start`; the "resume an old task" path moves to `continue`.
3. Add a task ID generator in the service layer that derives the day-based sequence from store data.
4. Add a store query for counting tasks created on a specific day.
5. Change the countdown helper so interruption does not close the session.
6. Update CLI control flow so `start`, `continue`, and `watch` each handle countdown entry and interruption explicitly.
7. Trim `remaining` from the default `status` formatter.
8. Update README examples and manual demo flow to reflect `continue` and `watch`.

## Test Plan

### Parser tests

- `watch` parses.
- `continue --minutes 25` parses and implies latest-task behavior.
- `continue --task-id <id> --minutes 25` parses.
- `start` still requires `--task`.
- `start --latest` is no longer accepted.

### Service tests

- New task IDs follow `YYYY-DDMM-NNNN`.
- Task IDs increment within the same day.
- Task IDs reset on the next day.
- `continue` resolves the latest task when no ID is provided.
- Existing slug-based task IDs can still be resumed and completed.

### CLI flow tests

- `start` creates the task, prints summary output, and enters countdown.
- `Ctrl+C` during `start` leaves the session active.
- `watch` attaches to the active session and `Ctrl+C` leaves it active.
- `continue` starts a new session for the latest task by default.
- `continue --task-id` starts a new session for the specified task.
- `status` no longer prints `remaining`.

### Timer tests

- Timer expiry still closes the session.
- External completion still exits the countdown cleanly.
- Keyboard interruption exits without closing the session.

## Risks And Non-Goals

### Risks

- Day-based ID generation depends on local wall-clock semantics. Tests should pin exact datetimes to avoid ambiguous rollover behavior.
- Users may still expect `status` to show live remaining time. README examples must make `watch` discoverable.

### Non-goals

- No background daemon or detached watcher process.
- No schema migration for old task IDs.
- No change to summary aggregation behavior.
