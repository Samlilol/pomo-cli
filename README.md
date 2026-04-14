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

    python3 -m pomo_cli plan --file today-plan.json
    python3 -m pomo_cli run --position 1
    python3 -m pomo_cli run --task-id 2026-1004-0001 --minutes 30
    python3 -m pomo_cli start --task "write 500-word essay" --minutes 25
    python3 -m pomo_cli continue --minutes 25
    python3 -m pomo_cli continue --task-id 2026-0604-0001 --minutes 25
    python3 -m pomo_cli watch
    python3 -m pomo_cli backlog
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

## Planning Flow

Create a JSON file with a parent title and planned subtasks:

    {
      "parent_title": "Today plan",
      "subtasks": [
        {"task_title": "Finish lecture 6", "estimate_minutes": 45, "priority": "high"},
        {"task_title": "Write notes", "estimate_minutes": 20, "priority": "medium"}
      ]
    }

Write it into today's backlog:

    python3 -m pomo_cli plan --file today-plan.json

Inspect the ordered backlog:

    python3 -m pomo_cli backlog

Start a planned backlog item by displayed position or explicit task id:

    python3 -m pomo_cli run --position 1
    python3 -m pomo_cli run --task-id 2026-1004-0001

Use `start` for brand new ad hoc tasks and `continue` for worked tasks that already have session history.

## Agent Sample Flows

These flows work well with Codex, Claude Code, or any other agent that can call Slack MCP, Linear MCP, and local CLI commands.

### Flow 1: Agent Finds Today Todo, Breaks It Down, Then Runs It

Use this when you want the agent to do more planning work up front.

1. User asks the agent to find today’s todos from Slack MCP and Linear MCP.
2. The agent collects candidate work items from Slack messages, Linear issues, or both.
3. The agent normalizes them into a short “today plan”.
4. The agent breaks each item into runnable subtasks with `estimate_minutes` and `priority`.
5. The agent writes a local JSON file such as `today-plan.json`.
6. The agent runs:

       python3 -m pomo_cli plan --file today-plan.json

7. The agent shows the resulting backlog:

       python3 -m pomo_cli backlog

8. The user replies with a selection such as `start 1`.
9. The agent maps that to the backlog position and runs:

       python3 -m pomo_cli run --position 1

This is the best fit when the source todo list is messy, spread across tools, or needs decomposition before starting work.

### Flow 2: Agent Finds Highest-Priority Todo and Starts Immediately

Use this when you want the fastest “just tell me what to do next” flow.

1. User asks the agent to find today’s highest-priority todo from Slack MCP and Linear MCP.
2. The agent resolves the best next task directly from those sources.
3. If the task already exists in today’s backlog, the agent starts it with:

       python3 -m pomo_cli run --task-id <planned-task-id>

4. If the task is not yet in the backlog, the agent can first create a one-item plan file and run:

       python3 -m pomo_cli plan --file today-plan.json
       python3 -m pomo_cli run --position 1

5. The countdown starts immediately and the user can later use:

       python3 -m pomo_cli watch
       python3 -m pomo_cli status
       python3 -m pomo_cli complete --latest

This is the best fit when the agent can confidently choose the next task without a separate planning round.
