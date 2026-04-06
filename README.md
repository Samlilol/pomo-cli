# pomo-cli

Local pomodoro CLI for agent-assisted workflows.

## Development

    cd pomo-cli
    python3 -m venv /tmp/pomo-cli-venv
    . /tmp/pomo-cli-venv/bin/activate
    python3 setup.py develop
    PYTHONPATH=src python3 -m unittest -v

If your checkout path does not contain spaces, a repo-local `.venv` also works. In a path like `/Users/samli/Desktop/Study Repo`, use a venv path without spaces so the generated `pomo` script has a valid interpreter path.

## Commands

    python3 -m pomo_cli start --task "write 500-word essay" --minutes 25
    python3 -m pomo_cli continue --minutes 25
    python3 -m pomo_cli continue --task-id 2026-0604-0001 --minutes 25
    python3 -m pomo_cli watch
    python3 -m pomo_cli complete --task-id 2026-0604-0001
    python3 -m pomo_cli complete --latest
    python3 -m pomo_cli status
    python3 -m pomo_cli summary

## Manual Demo Flow

1. Start a session in one terminal:

       pomo start --task "write 500-word essay" --minutes 1

2. Leave the countdown without ending the task:

       Ctrl+C

3. In a second terminal, inspect the active task:

       pomo status

4. Re-attach to the timer later:

       pomo watch

5. Continue the latest task with a new session:

       pomo continue --minutes 1

6. Complete the task early from the second terminal:

       pomo complete --latest

7. Inspect today’s worked-time summary:

       pomo summary

For a fresh data directory, set `HOME` to a temporary directory before running the commands.
