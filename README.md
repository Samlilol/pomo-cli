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
    python3 -m pomo_cli start --task-id write-500-word-essay --minutes 25
    python3 -m pomo_cli start --latest --minutes 25
    python3 -m pomo_cli complete --task-id write-500-word-essay
    python3 -m pomo_cli complete --latest
    python3 -m pomo_cli status
    python3 -m pomo_cli summary

## Manual Demo Flow

1. Start a session in one terminal:

       pomo start --task "write 500-word essay" --minutes 1

2. In a second terminal, inspect the active task:

       pomo status

3. Complete the task early from the second terminal:

       pomo complete --latest

4. Inspect today’s completed-work summary:

       pomo summary

For a fresh data directory, set `HOME` to a temporary directory before running the commands.
