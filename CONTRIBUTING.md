# Contributing to pomo-cli

## Dev Setup

```bash
cd pomo-cli
python3 -m venv /tmp/pomo-cli-venv
. /tmp/pomo-cli-venv/bin/activate
pip install -e .
```

Run the test suite with:

```bash
python -m unittest -v
```

Install the optional MCP extra when you want to run `pomo-mcp` or execute the
MCP integration tests locally instead of skipping them:

```bash
pip install -e ".[mcp]"
```

## Project Rules

- All time-dependent behavior must use injected `now_fn` and `sleep_fn` in tests. Do not introduce real sleeps into the test suite.
- New CLI commands should follow the existing flow in `CLAUDE.md`: parser change, handler branch, service method, store query if needed, then tests.
- New MCP tools must map to an existing or newly added `PomoService` method and must return JSON-serializable dict/list payloads only.
- New hard dependencies require explicit discussion before they land.

## MCP Trust Boundary

`pomo-mcp` is a local stdio server. It reads and writes the user's local `~/.pomo-cli/pomo.db`. Only connect it to trusted local agent clients. Do not expose it as a network service.

## Open Source Release Gate

Before publishing a public release:

1. Run a history-level secret scan with `gitleaks` or GitHub secret scanning.
2. Verify the built `sdist` and `wheel` only contain source, tests, docs, license, and package metadata.
3. Confirm no `.env`, key, cert, or similar private files are tracked.
4. Enable GitHub secret scanning / push protection if the repository will be public.
