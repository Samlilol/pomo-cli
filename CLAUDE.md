# pomo-cli

Local work observability runtime for agent-assisted workflows. SQLite-backed, pure Python, no dependencies beyond the standard library.

The canonical product definition lives in `PRD.md`.

## Dev Setup

```bash
cd pomo-cli
python3 -m venv /tmp/pomo-cli-venv
. /tmp/pomo-cli-venv/bin/activate
pip install -e .
pip install -e ".[mcp]"   # optional MCP server support
```

If your checkout path contains spaces (e.g. `/Users/you/Desktop/Study Repo`), use a venv path without spaces like `/tmp/pomo-cli-venv`. The generated `pomo` script needs a valid interpreter path.

## Running Tests

```bash
python -m unittest -v
```

All tests are in `tests/`. They use injected `now_fn` and `sleep_fn` so no real timers or sleeps run during the test suite.

## Architecture

```
cli.py       — argument parsing, command dispatch, output formatting
service.py   — PomoService: business logic, task/session lifecycle
store.py     — PomoStore: all SQLite reads and writes
models.py    — frozen dataclasses: TaskRecord, SessionRecord, BacklogEntry
timer.py     — run_countdown(): foreground terminal countdown loop
```

### Key constraints

- **`start`, `run`, and `continue` are non-blocking by default** — they print status and return immediately. Use `--watch` or `pomo watch` for the foreground countdown loop.
- **A task may not have more than one active session at a time** — the runtime allows multiple active sessions across different tasks, but planned-task `start` / `run` and `continue` reject opening a second active session for the same task.
- **Task IDs are CLI-owned** — format `YYYY-MMDD-NNNN`, generated from `count_tasks_created_on_date`. Agents must reuse the returned `task_id` to continue or complete a task.
- **`start` is the primary begin-work command** — `start --task` creates an ad hoc task; `start --position` and `start --task-id` start planned backlog tasks. `run` remains as a compatibility alias for planned tasks.
- **MCP follows the same start-first model** — `start_task(task_title, planned_minutes)` creates ad hoc tasks; `start_task(task_id=...)` and `start_task(position=...)` start planned backlog tasks. `run_planned_task` remains as a compatibility wrapper.
- **Elapsed time uses actual seconds**, not planned minutes. `finalize_session` accumulates real elapsed time into `tasks.total_elapsed_seconds`.
- **Summary is worked-today plus completed-today** — `pomo summary` reports tasks worked today, tasks completed today, total time spent today, and per-task elapsed entries.

### State machine

```
planned → running → session_closed → running  (via continue/start)
                 ↘               ↘
                  completed       completed
```

`session_closed` means a `watch` countdown ended but the task was not explicitly marked done. `completed` requires an explicit `pomo complete` call.

### Adding a new command

1. Add a subparser in `cli.py:build_parser()`
2. Add the handler branch in `cli.py:main()`
3. Add the business logic method to `PomoService` in `service.py`
4. Add any new store queries to `PomoStore` in `store.py`
5. Add tests in `tests/`
