# Phase 2 Plan: pomo-cli Open Source

## Context

Phase 1 shipped a working local Pomodoro CLI with clean architecture (cli → service → store), 76 passing tests, and agent docs (CLAUDE.md, AGENTS.md, Claude Code skill). Phase 2 opens it to all developers by adding a proper install path (PyPI), CI, an MCP server for agent-native integration, and a license.

---

## Work Items (in order)

### 1. MIT License
**Files:** `LICENSE` (new), `pyproject.toml`

- Add `LICENSE` file at repo root with standard MIT text, copyright "Sam Li 2026"
- Add `license = {text = "MIT"}` to `[project]` in `pyproject.toml`
- Add MIT badge to `README.md`

---

### 2. PyPI Packaging
**Files:** `pyproject.toml`, `setup.py` (delete), `CLAUDE.md`

- Harden `pyproject.toml` with full PEP 621 metadata: `authors`, `readme`, `license`, `classifiers`, `keywords`, `urls`, `requires-python = ">=3.10"`
- Delete `setup.py` — replaced entirely by `pyproject.toml`
- Split dependencies with extras:
  ```toml
  [project.optional-dependencies]
  mcp = ["mcp>=1.0.0,<2.0.0"]
  ```
- Add MCP server entry point:
  ```toml
  [project.scripts]
  pomo = "pomo_cli.cli:main"
  pomo-mcp = "pomo_cli.mcp_server:main"
  ```
- Update `CLAUDE.md` dev setup: `pip install -e .` / `pip install -e ".[mcp]"`

**Acceptance:** `pip install .` in fresh venv → working `pomo` with zero external deps. `python3 -m build` + `twine check dist/*` pass clean.

---

### 3. GitHub Actions CI
**Files:** `.github/workflows/ci.yml` (new)

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: pip install -e ".[mcp]"
      - run: PYTHONPATH=src python3 -m unittest -v
```

No linting, no auto-publish — keep it minimal for launch.

**Acceptance:** Green badge on `main`. Breaking test → red CI on PR.

---

### 4. MCP Server
**Files:** `src/pomo_cli/mcp_server.py` (new), `AGENTS.md`, `.claude/skills/pomo/SKILL.md`

#### Architecture
- Single new file `mcp_server.py` — flat, consistent with existing module structure
- Reuses `PomoService` + `PomoStore` directly (same `default_db_path()` from `cli.py`)
- Transport: `stdio` only (works with Claude Code, Codex, Cursor, Windsurf)
- **No countdown loop** — MCP tools are fire-and-forget; agents poll `get_status`

#### Tools (8 total)

| Tool | Maps to | Returns |
|---|---|---|
| `start_task(task_title, planned_minutes)` | `service.start_new_task()` | status dict |
| `complete_task(task_id, use_latest?)` | `service.complete_task()` | status dict |
| `get_status()` | `service.get_status()` | status dict |
| `get_summary(date?)` | `service.summary_for_date()` | summary dict |
| `get_backlog(date?)` | `service.backlog_for_date()` | list of backlog entries |
| `plan_tasks(parent_title, subtasks[])` | `service.plan_tasks()` | list of task records |
| `run_planned_task(task_id?, position?, planned_minutes?)` | `service.run_planned_task()` | status dict |
| `continue_task(task_id?, planned_minutes)` | `service.continue_task()` | status dict |

#### Serialization
- Private `_to_dict()` helper inside `mcp_server.py` only — converts dataclasses to dicts, `datetime` → `.isoformat()`, `None` → `null`
- Do NOT add `to_dict()` to existing models
- Errors: catch `RuntimeError`/`KeyError`, return `{"error": "<message>"}` — not MCP protocol errors

#### Client config (add to AGENTS.md + SKILL.md)
```json
// Claude Code: ~/.claude/claude_code_config.json
{ "mcpServers": { "pomo": { "command": "pomo-mcp", "args": [] } } }

// Cursor: .cursor/mcp.json  (same structure)
// Windsurf: ~/.codeium/windsurf/mcp_config.json  (same structure)
```

#### Known limitations to document
- No `watch` MCP tool — agents poll `get_status` instead
- Running CLI + MCP simultaneously may race on session creation (SQLite unique index prevents double-open, but document "don't mix" for now)
- Sessions started via MCP stay `running` until `complete_task` is called — no auto-close timer

**Acceptance:**
- `pomo-mcp` starts, 8 tools visible, exits cleanly on stdin close
- `start_task` → `get_status` returns `running`
- `complete_task` returns `completed`
- `plan_tasks` → `get_backlog` shows entries
- Double `start_task` returns `{"error": "an active session is already running"}`

---

### 5. CONTRIBUTING.md
**Files:** `CONTRIBUTING.md` (new)

- Dev setup (`pip install -e ".[mcp]"`, run tests)
- Rule: all time-dependent code uses injected `now_fn`/`sleep_fn` — no real timers in tests
- Adding a CLI command: link to CLAUDE.md 4-step process
- Adding an MCP tool: must map to a service method, must return JSON-serializable dict
- PR requirements: tests pass on all 3 Python versions, no new hard dependencies without discussion

---

## Critical Files

| File | Action |
|---|---|
| `pyproject.toml` | Harden metadata, add extras, add `pomo-mcp` entry point |
| `setup.py` | Delete |
| `src/pomo_cli/mcp_server.py` | Create (new) |
| `src/pomo_cli/cli.py` | Reuse `default_db_path()`, `build_service()` — no changes needed |
| `src/pomo_cli/service.py` | No changes — all 8 tools map directly to existing methods |
| `src/pomo_cli/store.py` | No changes |
| `LICENSE` | Create (new) |
| `.github/workflows/ci.yml` | Create (new) |
| `CONTRIBUTING.md` | Create (new) |
| `AGENTS.md` | Add MCP client config section |
| `.claude/skills/pomo/SKILL.md` | Add MCP client config section |
| `CLAUDE.md` | Update dev setup command |
| `README.md` | Add MIT badge |

## Out of Scope for Phase 2
- SSE / HTTP MCP transport
- Auto-publish to PyPI via CI
- `ruff`, `mypy`, pre-commit hooks
- Windows validation
- Web dashboard / TUI
