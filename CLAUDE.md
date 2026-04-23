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

- **A task may not have more than one active session at a time** — the runtime allows multiple active sessions across different tasks, but `run` / `continue` reject opening a second active session for the same task.
- **Task IDs are CLI-owned** — format `YYYY-MMDD-NNNN`, generated from `count_tasks_created_on_date`. Agents must reuse the returned `task_id` to continue or complete a task.
- **Elapsed time uses actual seconds**, not planned minutes. `finalize_session` accumulates real elapsed time into `tasks.total_elapsed_seconds`.
- **Summary is worked-today plus completed-today** — `pomo summary` reports tasks worked today, tasks completed today, total time spent today, and per-task elapsed entries.

### State machine

```
planned → running → session_closed → running  (via continue/run)
                 ↘               ↘
                  completed       completed
```

`session_closed` means the timer ended but the task was not explicitly marked done. `completed` requires an explicit `pomo complete` call.

### Adding a new command

1. Add a subparser in `cli.py:build_parser()`
2. Add the handler branch in `cli.py:main()`
3. Add the business logic method to `PomoService` in `service.py`
4. Add any new store queries to `PomoStore` in `store.py`
5. Add tests in `tests/`
