# pomo-cli

Local Pomodoro CLI for agent-assisted workflows. SQLite-backed, pure Python, no dependencies beyond the standard library.

## Dev Setup

```bash
cd pomo-cli
python3 -m venv /tmp/pomo-cli-venv
. /tmp/pomo-cli-venv/bin/activate
python3 setup.py develop
```

If your checkout path contains spaces (e.g. `/Users/you/Desktop/Study Repo`), use a venv path without spaces like `/tmp/pomo-cli-venv`. The generated `pomo` script needs a valid interpreter path.

## Running Tests

```bash
PYTHONPATH=src python3 -m unittest -v
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

- **One active session at a time** — enforced by a SQLite partial unique index on `sessions WHERE ended_at IS NULL`. Any command that opens a new session calls `_assert_no_running_session()` first.
- **Task IDs are CLI-owned** — format `YYYY-DDMM-NNNN`, generated from `count_tasks_created_on_date`. Agents must reuse the returned `task_id` to continue or complete a task.
- **Elapsed time uses actual seconds**, not planned minutes. `finalize_session` accumulates real elapsed time into `tasks.total_elapsed_seconds`.
- **Summary buckets by `completed_at`** — only explicitly completed tasks appear in `pomo summary`.

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
